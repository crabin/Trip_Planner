"""
报告格式化节点
负责将最终研究结果格式化为美观的Markdown报告
"""

import json
import re
from typing import List, Dict, Any

from .base_node import BaseNode
from loguru import logger
from ..prompts import SYSTEM_PROMPT_REPORT_FORMATTING


REQUIRED_GUIDE_SECTIONS = (
    "行前先做",
    "每日行程",
    "交通与住宿方案",
    "景点、餐饮与备选池",
    "行李检查清单",
    "预算",
    "实用提示与风险预案",
    "出发前一致性检查",
    "资料来源与更新说明",
)

CONVERSATIONAL_TAIL_PATTERNS = (
    re.compile(r"如果你愿意"),
    re.compile(r"如果你需要"),
    re.compile(r"如需(?:要)?我"),
    re.compile(r"我(?:还)?可以(?:继续|再|为你)"),
    re.compile(r"下一步(?:我)?可以"),
    re.compile(r"欢迎(?:继续)?(?:告诉|提供|补充)"),
)


def _extract_markdown_document(output: str) -> str:
    """Extract the Markdown document without treating brackets as JSON markers."""
    text = output.strip()
    fenced_match = re.fullmatch(
        r"```(?:markdown|md)?\s*\n(?P<body>.*)\n```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if fenced_match:
        text = fenced_match.group("body").strip()

    title_match = re.search(r"(?m)^#\s+\S", text)
    if title_match and title_match.start() > 0:
        text = text[title_match.start():]
    return text.strip()


def _is_conversational_line(line: str) -> bool:
    return any(pattern.search(line) for pattern in CONVERSATIONAL_TAIL_PATTERNS)


def _strip_conversational_tail(markdown: str) -> str:
    """Remove chat-style offers appended after the final document section."""
    lines = markdown.rstrip().splitlines()
    while lines:
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and _is_conversational_line(lines[-1]):
            lines.pop()
            continue
        break
    return "\n".join(lines).strip()


def _validate_final_guide(markdown: str) -> None:
    """Reject partial or conversational output before it is persisted as final."""
    lines = markdown.splitlines()
    if not lines or not re.match(r"^#\s+\S", lines[0]):
        raise ValueError("最终攻略缺少一级标题")

    headings = [line[3:].strip() for line in lines if line.startswith("## ")]
    missing_sections = [
        section
        for section in REQUIRED_GUIDE_SECTIONS
        if not any(heading.startswith(section) for heading in headings)
    ]
    if missing_sections:
        raise ValueError(f"最终攻略缺少必要章节: {', '.join(missing_sections)}")

    conversational_lines = [line for line in lines if _is_conversational_line(line)]
    if conversational_lines:
        raise ValueError("最终攻略包含对话式追问或后续服务邀约")


class ReportFormattingNode(BaseNode):
    """格式化最终报告的节点"""
    
    def __init__(self, llm_client):
        """
        初始化报告格式化节点
        
        Args:
            llm_client: LLM客户端
        """
        super().__init__(llm_client, "ReportFormattingNode")
    
    def validate_input(self, input_data: Any) -> bool:
        """验证输入数据"""
        if isinstance(input_data, str):
            try:
                data = json.loads(input_data)
                return self.validate_input(data)
            except (json.JSONDecodeError, TypeError):
                return False
        if isinstance(input_data, list):
            return all(
                isinstance(item, dict) and "title" in item and "paragraph_latest_state" in item
                for item in input_data
            )
        if isinstance(input_data, dict):
            sections = input_data.get("sections")
            trip_context = input_data.get("trip_context")
            return bool(trip_context) and isinstance(sections, list) and all(
                isinstance(item, dict) and "title" in item and "paragraph_latest_state" in item
                for item in sections
            )
        return False
    
    def run(self, input_data: Any, **kwargs) -> str:
        """
        调用LLM生成Markdown格式报告
        
        Args:
            input_data: 包含所有段落信息的列表
            **kwargs: 额外参数
            
        Returns:
            格式化的Markdown报告
        """
        try:
            if not self.validate_input(input_data):
                raise ValueError(
                    "输入数据格式错误，需要旅行上下文和包含title、paragraph_latest_state的sections"
                )
            
            # 准备输入数据
            if isinstance(input_data, str):
                message = input_data
            else:
                message = json.dumps(input_data, ensure_ascii=False)
            
            logger.info("正在格式化最终报告")
            
            # 调用LLM生成Markdown格式（流式，安全拼接UTF-8）
            response = self.llm_client.stream_invoke_to_string(
                SYSTEM_PROMPT_REPORT_FORMATTING,
                message,
            )

            try:
                processed_response = self.process_output(response)
            except ValueError as validation_error:
                logger.warning("最终攻略首次校验失败，进行一次完整重写: {}", validation_error)
                retry_message = (
                    message
                    + "\n\n<RETRY_REQUIREMENT>"
                    + "上一稿未通过最终文档校验："
                    + str(validation_error)
                    + "。请根据原始研究底稿重新输出一份从标题到资料来源都完整的Markdown攻略，"
                    + "不要解释校验错误，不要省略章节，不要添加追问或后续服务邀约。"
                    + "</RETRY_REQUIREMENT>"
                )
                retry_response = self.llm_client.stream_invoke_to_string(
                    SYSTEM_PROMPT_REPORT_FORMATTING,
                    retry_message,
                )
                processed_response = self.process_output(retry_response)
            
            logger.info("成功生成格式化报告")
            return processed_response
            
        except Exception as e:
            logger.exception(f"报告格式化失败: {str(e)}")
            raise
    
    def process_output(self, output: str) -> str:
        """
        处理LLM输出，清理Markdown格式
        
        Args:
            output: LLM原始输出
            
        Returns:
            清理后的Markdown报告
        """
        cleaned_output = _extract_markdown_document(output)

        # 确保报告有基本结构
        if not cleaned_output.strip():
            raise ValueError("LLM返回了空的旅行攻略")

        cleaned_output = _strip_conversational_tail(cleaned_output)
        _validate_final_guide(cleaned_output)
        return cleaned_output
    
    def format_report_manually(self, paragraphs_data: List[Dict[str, str]], 
                             report_title: str = "目的地旅行攻略") -> str:
        """
        手动格式化报告（备用方法）
        
        Args:
            paragraphs_data: 段落数据列表
            report_title: 报告标题
            
        Returns:
            格式化的Markdown报告
        """
        try:
            logger.info("使用手动格式化方法")
            
            # 构建报告
            report_lines = [
                f"# {report_title}",
                "",
                "---",
                ""
            ]
            
            # 添加各个段落
            for i, paragraph in enumerate(paragraphs_data, 1):
                title = paragraph.get("title", f"段落 {i}")
                content = paragraph.get("paragraph_latest_state", "")
                
                if content:
                    report_lines.extend([
                        f"## {title}",
                        "",
                        content,
                        "",
                        "---",
                        ""
                    ])
            
            # 添加出发前复核提醒
            if len(paragraphs_data) > 1:
                report_lines.extend([
                    "## 出发前复核",
                    "",
                    "请在出发前再次核验交通班次、住宿晚数、景点开放与预约、"
                    "天气预警和价格库存等动态信息。",
                    ""
                ])
            
            return "\n".join(report_lines)
            
        except Exception as e:
            logger.exception(f"手动格式化失败: {str(e)}")
            return "# 旅行攻略生成失败\n\n无法完成攻略格式化。"
