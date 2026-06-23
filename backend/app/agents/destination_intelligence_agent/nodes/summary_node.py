"""
总结节点实现
负责根据搜索结果生成和更新段落内容
"""

import json
from typing import Any
from json.decoder import JSONDecodeError
from loguru import logger

from .base_node import StateMutationNode
from ..state.state import State
from ..prompts import SYSTEM_PROMPT_FIRST_SUMMARY, SYSTEM_PROMPT_REFLECTION_SUMMARY
from ..utils.text_processing import (
    clean_json_tags,
    fix_incomplete_json,
)


def _extract_summary_content(output: str, field_name: str, label: str) -> str:
    """Extract one summary field without leaking malformed JSON into state."""
    cleaned_output = clean_json_tags(output).strip()
    object_start = cleaned_output.find("{")
    if object_start >= 0:
        cleaned_output = cleaned_output[object_start:].strip()
    logger.debug("已清理{}输出，长度: {}", label, len(cleaned_output))

    try:
        result = json.loads(cleaned_output)
        logger.info("JSON解析成功")
    except JSONDecodeError as parse_error:
        # `json.loads` rejects a valid object followed by prose or another value.
        # `raw_decode` safely returns the first complete JSON value and its end.
        try:
            result, end_index = json.JSONDecoder().raw_decode(cleaned_output)
        except JSONDecodeError:
            fixed_json = fix_incomplete_json(cleaned_output)
            if not fixed_json:
                if cleaned_output.lstrip().startswith(("{", "[")):
                    logger.warning(
                        "{}JSON无法解析或修复，拒绝将结构化残片写入总结",
                        label,
                    )
                    return ""
                logger.warning("{}不是JSON，使用纯文本兜底", label)
                return cleaned_output.strip()

            try:
                result = json.loads(fixed_json)
                logger.info("JSON修复成功")
            except JSONDecodeError:
                logger.warning(
                    "{}JSON修复结果仍无效，拒绝将结构化残片写入总结",
                    label,
                )
                return ""
        else:
            trailing_text = cleaned_output[end_index:].strip()
            logger.warning(
                "{}包含JSON后的额外内容（{}字符，原错误: {}），已忽略",
                label,
                len(trailing_text),
                parse_error.msg,
            )

    if not isinstance(result, dict):
        logger.warning("{}顶层不是JSON对象", label)
        return ""

    summary = result.get(field_name)
    if isinstance(summary, str) and summary.strip():
        return summary.strip()

    logger.warning("{}缺少有效字段: {}", label, field_name)
    return ""


def _build_first_summary_fallback(data: dict[str, Any]) -> str:
    """Build a conservative paragraph draft when the LLM misses the JSON contract."""
    title = str(data.get("title") or "研究部分").strip()
    content = str(data.get("content") or "").strip()
    trip_context = str(data.get("trip_context") or "").strip()
    search_query = str(data.get("search_query") or "").strip()
    raw_results = data.get("search_results") or []
    if isinstance(raw_results, str):
        search_results = [raw_results]
    elif isinstance(raw_results, list):
        search_results = [str(item).strip() for item in raw_results if str(item).strip()]
    else:
        search_results = []

    lines = [
        f"## {title}",
        "",
        "### 研究目标",
        content or "围绕本段目标整理可执行旅行信息。",
    ]
    if trip_context:
        lines.extend(["", "### 旅行请求", trip_context])
    if search_query:
        lines.extend(["", "### 已执行搜索", f"- {search_query}"])
    if search_results:
        lines.extend(["", "### 搜索结果摘录"])
        for index, result in enumerate(search_results[:5], start=1):
            lines.append(f"{index}. {result[:1200]}")
    else:
        lines.extend(["", "### 待补充", "- 本轮没有可用搜索结果，后续反思搜索需继续核查。"])
    lines.extend(
        [
            "",
            "### 待确认项",
            "- 开放时间、票价、班次、库存和预约政策需在出行前通过官方渠道复核。",
        ]
    )
    return "\n".join(lines).strip()


class FirstSummaryNode(StateMutationNode):
    """根据搜索结果生成段落首次总结的节点"""
    
    def __init__(self, llm_client):
        """
        初始化首次总结节点
        
        Args:
            llm_client: LLM客户端
        """
        super().__init__(llm_client, "FirstSummaryNode")
    
    def validate_input(self, input_data: Any) -> bool:
        """验证输入数据"""
        if isinstance(input_data, str):
            try:
                data = json.loads(input_data)
                required_fields = ["title", "content", "search_query", "search_results"]
                return all(field in data for field in required_fields)
            except JSONDecodeError:
                return False
        elif isinstance(input_data, dict):
            required_fields = ["title", "content", "search_query", "search_results"]
            return all(field in input_data for field in required_fields)
        return False
    
    def run(self, input_data: Any, **kwargs) -> str:
        """
        调用LLM生成段落总结
        
        Args:
            input_data: 包含title、content、search_query和search_results的数据
            **kwargs: 额外参数
            
        Returns:
            段落总结内容
        """
        try:
            if not self.validate_input(input_data):
                raise ValueError("输入数据格式错误")
            
            # 准备输入数据
            if isinstance(input_data, str):
                data = json.loads(input_data)
            else:
                data = input_data.copy() if isinstance(input_data, dict) else input_data
            
            # 转换为JSON字符串
            message = json.dumps(data, ensure_ascii=False)
            
            logger.info("正在生成首次段落总结")
            
            # 调用LLM生成总结（流式，安全拼接UTF-8）
            try:
                response = self.llm_client.stream_invoke_to_string(
                    SYSTEM_PROMPT_FIRST_SUMMARY,
                    message,
                )
            except Exception as exc:
                logger.warning("首次总结LLM调用失败，使用搜索结果兜底: {}", exc)
                return _build_first_summary_fallback(data)
            
            # 处理响应
            processed_response = self.process_output(response)
            if not processed_response:
                processed_response = _build_first_summary_fallback(data)
                logger.warning("首次总结响应不符合 paragraph_latest_state 输出契约，已使用兜底底稿")
            
            logger.info("成功生成首次段落总结")
            return processed_response
            
        except Exception as e:
            logger.exception(f"生成首次总结失败: {str(e)}")
            raise
    
    def process_output(self, output: str) -> str:
        """
        处理LLM输出，提取段落内容
        
        Args:
            output: LLM原始输出
            
        Returns:
            段落内容
        """
        return _extract_summary_content(
            output,
            "paragraph_latest_state",
            "首次总结",
        )
    
    def mutate_state(self, input_data: Any, state: State, paragraph_index: int, **kwargs) -> State:
        """
        更新段落的最新总结到状态
        
        Args:
            input_data: 输入数据
            state: 当前状态
            paragraph_index: 段落索引
            **kwargs: 额外参数
            
        Returns:
            更新后的状态
        """
        try:
            # 生成总结
            summary = self.run(input_data, **kwargs)
            
            # 更新状态
            if 0 <= paragraph_index < len(state.paragraphs):
                state.paragraphs[paragraph_index].research.latest_summary = summary
                logger.info(f"已更新段落 {paragraph_index} 的首次总结")
            else:
                raise ValueError(f"段落索引 {paragraph_index} 超出范围")
            
            state.update_timestamp()
            return state
            
        except Exception as e:
            logger.exception(f"状态更新失败: {str(e)}")
            raise


class ReflectionSummaryNode(StateMutationNode):
    """根据反思搜索结果更新段落总结的节点"""
    
    def __init__(self, llm_client):
        """
        初始化反思总结节点
        
        Args:
            llm_client: LLM客户端
        """
        super().__init__(llm_client, "ReflectionSummaryNode")
    
    def validate_input(self, input_data: Any) -> bool:
        """验证输入数据"""
        if isinstance(input_data, str):
            try:
                data = json.loads(input_data)
                required_fields = ["title", "content", "search_query", "search_results", "paragraph_latest_state"]
                return all(field in data for field in required_fields)
            except JSONDecodeError:
                return False
        elif isinstance(input_data, dict):
            required_fields = ["title", "content", "search_query", "search_results", "paragraph_latest_state"]
            return all(field in input_data for field in required_fields)
        return False
    
    def run(self, input_data: Any, **kwargs) -> str:
        """
        调用LLM更新段落内容
        
        Args:
            input_data: 包含完整反思信息的数据
            **kwargs: 额外参数
            
        Returns:
            更新后的段落内容
        """
        try:
            if not self.validate_input(input_data):
                raise ValueError("输入数据格式错误")
            
            # 准备输入数据
            if isinstance(input_data, str):
                data = json.loads(input_data)
            else:
                data = input_data.copy() if isinstance(input_data, dict) else input_data
            
            # 转换为JSON字符串
            message = json.dumps(data, ensure_ascii=False)
            
            logger.info("正在生成反思总结")
            
            # 调用LLM生成总结（流式，安全拼接UTF-8）
            response = self.llm_client.stream_invoke_to_string(
                SYSTEM_PROMPT_REFLECTION_SUMMARY,
                message,
            )
            
            # 处理响应
            processed_response = self.process_output(response)
            if not processed_response:
                processed_response = str(data["paragraph_latest_state"])
                logger.warning("反思总结响应无效，保留上一版段落总结")
            
            logger.info("成功生成反思总结")
            return processed_response
            
        except Exception as e:
            logger.exception(f"生成反思总结失败: {str(e)}")
            raise
    
    def process_output(self, output: str) -> str:
        """
        处理LLM输出，提取更新后的段落内容
        
        Args:
            output: LLM原始输出
            
        Returns:
            更新后的段落内容
        """
        return _extract_summary_content(
            output,
            "updated_paragraph_latest_state",
            "反思总结",
        )
    
    def mutate_state(self, input_data: Any, state: State, paragraph_index: int, **kwargs) -> State:
        """
        将更新后的总结写入状态
        
        Args:
            input_data: 输入数据
            state: 当前状态
            paragraph_index: 段落索引
            **kwargs: 额外参数
            
        Returns:
            更新后的状态
        """
        try:
            # 生成更新后的总结
            updated_summary = self.run(input_data, **kwargs)
            
            # 更新状态
            if 0 <= paragraph_index < len(state.paragraphs):
                state.paragraphs[paragraph_index].research.latest_summary = updated_summary
                state.paragraphs[paragraph_index].research.increment_reflection()
                logger.info(f"已更新段落 {paragraph_index} 的反思总结")
            else:
                raise ValueError(f"段落索引 {paragraph_index} 超出范围")
            
            state.update_timestamp()
            return state
            
        except Exception as e:
            logger.exception(f"状态更新失败: {str(e)}")
            raise
