"""
搜索节点实现
负责生成搜索查询和反思查询
"""

import json
from typing import Dict, Any
from json.decoder import JSONDecodeError
from loguru import logger

from .base_node import BaseNode
from ..prompts import SYSTEM_PROMPT_FIRST_SEARCH, SYSTEM_PROMPT_REFLECTION
from ..utils import (
    remove_reasoning_from_output,
    clean_json_tags,
    extract_clean_response,
)


SEARCH_TOOLS = frozenset(
    {
        "basic_search_news",
        "deep_search_news",
        "search_news_last_24_hours",
        "search_news_last_week",
        "search_images_for_news",
        "search_news_by_date",
        "train_ticket_query",
    }
)


def _parse_search_plan(
    output: str,
    fallback_query: str,
    fallback_reason: str,
) -> Dict[str, str]:
    """Parse and validate the LLM search-plan contract without dropping fields."""
    cleaned_output = clean_json_tags(remove_reasoning_from_output(output))
    logger.debug("已清理搜索计划输出，长度: {}", len(cleaned_output))
    result = extract_clean_response(cleaned_output)

    if not isinstance(result, dict) or "error" in result:
        return {
            "search_query": fallback_query,
            "search_tool": "basic_search_news",
            "reasoning": fallback_reason,
        }

    search_query = str(result.get("search_query") or "").strip()
    if not search_query:
        return {
            "search_query": fallback_query,
            "search_tool": "basic_search_news",
            "reasoning": fallback_reason,
        }

    requested_tool = str(result.get("search_tool") or "basic_search_news")
    search_tool = requested_tool if requested_tool in SEARCH_TOOLS else "basic_search_news"
    plan = {
        "search_query": search_query,
        "search_tool": search_tool,
        "reasoning": str(result.get("reasoning") or "").strip(),
    }

    if search_tool == "search_news_by_date":
        for field_name in ("start_date", "end_date"):
            field_value = result.get(field_name)
            if field_value:
                plan[field_name] = str(field_value).strip()

    return plan


def _fallback_query(input_data: Dict[str, Any], suffix: str) -> str:
    """Build a useful fallback query from the trip rather than generic filler."""
    context = str(input_data.get("trip_context") or "").strip()
    title = str(input_data.get("title") or "").strip()
    query = " ".join(part for part in (context, title, suffix) if part)
    return query[:500] or suffix


class FirstSearchNode(BaseNode):
    """为段落生成首次搜索查询的节点"""
    
    def __init__(self, llm_client):
        """
        初始化首次搜索节点
        
        Args:
            llm_client: LLM客户端
        """
        super().__init__(llm_client, "FirstSearchNode")
    
    def validate_input(self, input_data: Any) -> bool:
        """验证输入数据"""
        if isinstance(input_data, str):
            try:
                data = json.loads(input_data)
                return "title" in data and "content" in data
            except JSONDecodeError:
                return False
        elif isinstance(input_data, dict):
            return "title" in input_data and "content" in input_data
        return False
    
    def run(self, input_data: Any, **kwargs) -> Dict[str, str]:
        """
        调用LLM生成搜索查询和理由
        
        Args:
            input_data: 包含title和content的字符串或字典
            **kwargs: 额外参数
            
        Returns:
            包含search_query和reasoning的字典
        """
        try:
            if not self.validate_input(input_data):
                raise ValueError("输入数据格式错误，需要包含title和content字段")
            
            # 准备输入数据
            data = json.loads(input_data) if isinstance(input_data, str) else input_data
            message = json.dumps(data, ensure_ascii=False)
            
            logger.info("正在生成首次搜索查询")
            
            # 调用LLM
            response = self.llm_client.stream_invoke_to_string(SYSTEM_PROMPT_FIRST_SEARCH, message)
            
            # 处理响应
            processed_response = self.process_output(
                response,
                fallback_query=_fallback_query(data, "官方旅行信息核查"),
            )
            
            logger.info(f"生成搜索查询: {processed_response.get('search_query', 'N/A')}")
            return processed_response
            
        except Exception as e:
            logger.exception(f"生成首次搜索查询失败: {str(e)}")
            raise
    
    def process_output(
        self,
        output: str,
        fallback_query: str = "目的地官方旅行信息核查",
    ) -> Dict[str, str]:
        """
        处理LLM输出，提取搜索查询和推理
        
        Args:
            output: LLM原始输出
            
        Returns:
            包含search_query和reasoning的字典
        """
        return _parse_search_plan(
            output,
            fallback_query,
            "LLM搜索计划无效，改用行程上下文构造的基础搜索",
        )
    
    def _get_default_search_query(self) -> Dict[str, str]:
        """
        获取默认搜索查询
        
        Returns:
            默认的搜索查询字典
        """
        return {
            "search_query": "目的地官方旅行信息核查",
            "search_tool": "basic_search_news",
            "reasoning": "由于解析失败，使用默认搜索查询"
        }


class ReflectionNode(BaseNode):
    """反思段落并生成新搜索查询的节点"""
    
    def __init__(self, llm_client):
        """
        初始化反思节点
        
        Args:
            llm_client: LLM客户端
        """
        super().__init__(llm_client, "ReflectionNode")
    
    def validate_input(self, input_data: Any) -> bool:
        """验证输入数据"""
        if isinstance(input_data, str):
            try:
                data = json.loads(input_data)
                required_fields = ["title", "content", "paragraph_latest_state"]
                return all(field in data for field in required_fields)
            except JSONDecodeError:
                return False
        elif isinstance(input_data, dict):
            required_fields = ["title", "content", "paragraph_latest_state"]
            return all(field in input_data for field in required_fields)
        return False
    
    def run(self, input_data: Any, **kwargs) -> Dict[str, str]:
        """
        调用LLM反思并生成搜索查询
        
        Args:
            input_data: 包含title、content和paragraph_latest_state的字符串或字典
            **kwargs: 额外参数
            
        Returns:
            包含search_query和reasoning的字典
        """
        try:
            if not self.validate_input(input_data):
                raise ValueError("输入数据格式错误，需要包含title、content和paragraph_latest_state字段")
            
            # 准备输入数据
            data = json.loads(input_data) if isinstance(input_data, str) else input_data
            message = json.dumps(data, ensure_ascii=False)
            
            logger.info("正在进行反思并生成新搜索查询")
            
            # 调用LLM
            response = self.llm_client.stream_invoke_to_string(SYSTEM_PROMPT_REFLECTION, message)
            
            # 处理响应
            processed_response = self.process_output(
                response,
                fallback_query=_fallback_query(data, "缺失信息补充核查"),
            )
            
            logger.info(f"反思生成搜索查询: {processed_response.get('search_query', 'N/A')}")
            return processed_response
            
        except Exception as e:
            logger.exception(f"反思生成搜索查询失败: {str(e)}")
            raise
    
    def process_output(
        self,
        output: str,
        fallback_query: str = "目的地缺失信息补充核查",
    ) -> Dict[str, str]:
        """
        处理LLM输出，提取搜索查询和推理
        
        Args:
            output: LLM原始输出
            
        Returns:
            包含search_query和reasoning的字典
        """
        return _parse_search_plan(
            output,
            fallback_query,
            "LLM反思计划无效，改用行程上下文补充核查",
        )
    
    def _get_default_reflection_query(self) -> Dict[str, str]:
        """
        获取默认反思搜索查询
        
        Returns:
            默认的反思搜索查询字典
        """
        return {
            "search_query": "目的地缺失信息补充核查",
            "search_tool": "basic_search_news",
            "reasoning": "由于解析失败，使用默认反思搜索查询"
        }
