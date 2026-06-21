"""Normalize provider responses without coupling nodes to a response class."""


def response_content_to_text(response: object) -> str:
    """Convert scalar or multimodal message content into plain text."""
    content = getattr(response, "content", "")
    if isinstance(content, list):
        content = "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content)


def extract_json_object(raw_text: str) -> str | None:
    """从模型原始文本中尽量提取 JSON 对象字符串。"""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()

    start_index = text.find("{")
    end_index = text.rfind("}")
    if start_index == -1 or end_index == -1 or end_index <= start_index:
        return None
    return text[start_index : end_index + 1]
