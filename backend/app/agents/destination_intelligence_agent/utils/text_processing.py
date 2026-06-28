"""
文本处理工具函数
用于清理LLM输出、解析JSON等
"""

import re
import json
from typing import Any, Dict, List
from json.decoder import JSONDecodeError


def clean_json_tags(text: str) -> str:
    """
    清理文本中的JSON标签
    
    Args:
        text: 原始文本
        
    Returns:
        清理后的文本
    """
    # 移除```json 和 ```标签
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*$', '', text)
    text = re.sub(r'```', '', text)
    
    return text.strip()


def clean_markdown_tags(text: str) -> str:
    """
    清理文本中的Markdown标签
    
    Args:
        text: 原始文本
        
    Returns:
        清理后的文本
    """
    # 移除```markdown 和 ```标签
    text = re.sub(r'```markdown\s*', '', text)
    text = re.sub(r'```\s*$', '', text)
    text = re.sub(r'```', '', text)
    
    return text.strip()


def remove_reasoning_from_output(text: str) -> str:
    """
    移除输出中的推理过程文本
    
    Args:
        text: 原始文本
        
    Returns:
        清理后的文本
    """
    # 查找JSON开始位置
    json_start = -1
    
    # 尝试找到第一个 { 或 [
    for i, char in enumerate(text):
        if char in '{[':
            json_start = i
            break
    
    if json_start != -1:
        # 从JSON开始位置截取
        return text[json_start:].strip()
    
    # 如果没有找到JSON标记，尝试其他方法
    # 移除常见的推理标识
    patterns = [
        r'(?:reasoning|推理|思考|分析)[:：]\s*.*?(?=\{|\[)',  # 移除推理部分
        r'(?:explanation|解释|说明)[:：]\s*.*?(?=\{|\[)',   # 移除解释部分
        r'^.*?(?=\{|\[)',  # 移除JSON前的所有文本
    ]
    
    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
    
    return text.strip()


def extract_clean_response(text: str) -> Any:
    """
    提取并清理响应中的JSON内容
    
    Args:
        text: 原始响应文本
        
    Returns:
        解析后的JSON字典
    """
    # 清理文本
    cleaned_text = clean_json_tags(text)
    cleaned_text = remove_reasoning_from_output(cleaned_text)
    
    # 尝试直接解析
    try:
        return json.loads(cleaned_text)
    except JSONDecodeError:
        pass
    
    # 尝试修复不完整的JSON
    fixed_text = fix_incomplete_json(cleaned_text)
    if fixed_text:
        try:
            return json.loads(fixed_text)
        except JSONDecodeError:
            pass
    
    # 尝试查找JSON对象
    json_pattern = r'\{.*\}'
    match = re.search(json_pattern, cleaned_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except JSONDecodeError:
            pass
    
    # 尝试查找JSON数组
    array_pattern = r'\[.*\]'
    match = re.search(array_pattern, cleaned_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except JSONDecodeError:
            pass
    
    # 如果所有方法都失败，返回错误信息
    return {"error": "JSON解析失败", "raw_text": cleaned_text}


def fix_incomplete_json(text: str) -> str:
    """
    修复不完整的JSON响应
    
    Args:
        text: 原始文本
        
    Returns:
        修复后的JSON文本，如果无法修复则返回空字符串
    """
    # 移除多余的逗号和空白
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*]', ']', text)
    
    # 检查是否已经是有效的JSON
    try:
        json.loads(text)
        return text
    except JSONDecodeError:
        pass
    
    # 只补齐缺失的结束括号，保持对象/数组的原始顶层类型。
    expected_closers: list[str] = []
    in_string = False
    escaped = False
    pairs = {"{": "}", "[": "]"}

    for char in text:
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char in pairs:
            expected_closers.append(pairs[char])
        elif char in ("}", "]"):
            if not expected_closers or expected_closers[-1] != char:
                return ""
            expected_closers.pop()

    if in_string:
        return ""
    text += "".join(reversed(expected_closers))
    
    # 验证修复后的JSON是否有效
    try:
        json.loads(text)
        return text
    except JSONDecodeError:
        # 如果仍然无效，尝试更激进的修复
        return fix_aggressive_json(text)


def fix_aggressive_json(text: str) -> str:
    """
    更激进的JSON修复方法
    
    Args:
        text: 原始文本
        
    Returns:
        修复后的JSON文本
    """
    # 查找所有可能的JSON对象
    objects = re.findall(r'\{[^{}]*\}', text)
    
    if len(objects) >= 2:
        # 如果有多个对象，包装成数组
        return '[' + ','.join(objects) + ']'
    elif len(objects) == 1:
        # 如果只有一个对象，保持对象契约
        return objects[0]
    else:
        # 不伪造一个看似有效但没有数据的结构
        return ''


def update_state_with_search_results(search_results: List[Dict[str, Any]], 
                                   paragraph_index: int, state: Any) -> Any:
    """
    将搜索结果更新到状态中
    
    Args:
        search_results: 搜索结果列表
        paragraph_index: 段落索引
        state: 状态对象
        
    Returns:
        更新后的状态对象
    """
    if 0 <= paragraph_index < len(state.paragraphs):
        # 获取最后一次搜索的查询（假设是当前查询）
        current_query = ""
        if search_results:
            # 从搜索结果推断查询（这里需要改进以获取实际查询）
            current_query = "搜索查询"
        
        # 添加搜索结果到状态
        state.paragraphs[paragraph_index].research.add_search_results(
            current_query, search_results
        )
    
    return state


def validate_json_schema(data: Dict[str, Any], required_fields: List[str]) -> bool:
    """
    验证JSON数据是否包含必需字段
    
    Args:
        data: 要验证的数据
        required_fields: 必需字段列表
        
    Returns:
        验证是否通过
    """
    return all(field in data for field in required_fields)


def truncate_content(content: str, max_length: int = 20000) -> str:
    """
    截断内容到指定长度
    
    Args:
        content: 原始内容
        max_length: 最大长度
        
    Returns:
        截断后的内容
    """
    if len(content) <= max_length:
        return content
    
    # 尝试在单词边界截断
    truncated = content[:max_length]
    last_space = truncated.rfind(' ')
    
    if last_space > max_length * 0.8:  # 如果最后一个空格位置合理
        return truncated[:last_space] + "..."
    else:
        return truncated + "..."


def format_search_results_for_prompt(
    search_results: List[Dict[str, Any]],
    max_length: int = 20000,
) -> List[str]:
    """
    格式化搜索结果用于提示词
    
    Args:
        search_results: 搜索结果列表
        max_length: 本轮搜索证据进入提示词的总字符预算
        
    Returns:
        格式化后的内容列表
    """
    results_with_content = [
        result
        for result in search_results
        if str(result.get("raw_content") or result.get("content") or "").strip()
    ]
    if not results_with_content:
        return []

    total_budget = max(200, int(max_length or 20000))
    per_result_budget = max(120, total_budget // len(results_with_content))
    formatted_results = []

    for result in results_with_content:
        content = str(result.get("raw_content") or result.get("content") or "").strip()
        metadata = [f"标题: {result.get('title') or '未提供'}"]
        if result.get("url"):
            metadata.append(f"URL: {result['url']}")
        if result.get("published_date"):
            metadata.append(f"发布日期: {result['published_date']}")
        if result.get("score") is not None:
            metadata.append(f"相关度: {result['score']}")

        metadata_prefix = "\n".join(metadata) + "\n内容: "
        content_budget = max(40, per_result_budget - len(metadata_prefix))
        truncated_content = truncate_content(content, content_budget)
        formatted_results.append(metadata_prefix + truncated_content)

    return formatted_results
