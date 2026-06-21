"""Trip-planning prompt templates."""

from app.models.schemas import TripRequest


SYSTEM_PROMPT = (
    "你是一名旅行规划助手。"
    "请用中文生成简洁的结构化旅行草稿。"
    "需要遵守用户给出的目的地、预算、节奏和本地攻略上下文。"
    "只能使用与用户目的地直接相关的攻略信息；如果上下文中出现其他城市、其他目的地或无关景点，必须忽略。"
    "你必须只输出一个 JSON 对象，不要输出 Markdown、解释文字或代码块。"
    "如果额外备注包含看日落、不想早起、少辣或拍照等明确诉求，要落实到具体某一天。"
)


def build_planner_messages(
    request: TripRequest,
    rag_contexts: list[str],
    day_count: int,
) -> list[tuple[str, str]]:
    """Build the provider-neutral messages for a complete trip draft."""
    guide_context = "\n\n".join(rag_contexts) if rag_contexts else "暂无本地攻略上下文。"
    human_prompt = f"""
目的地：{request.destination}
出发日期：{request.start_date.isoformat()}
结束日期：{request.end_date.isoformat()}
天数：{day_count}
人数：{request.travelers}
预算：{request.budget}
偏好：{'、'.join(request.preferences) if request.preferences else '无特别偏好'}
节奏：{request.pace or '适中'}
饮食偏好：{'、'.join(request.dietary_preferences) if request.dietary_preferences else '无'}
酒店档次：{request.hotel_level or '舒适型'}
额外备注：{request.special_notes or '无'}

本地攻略上下文：
{guide_context}

要求：
1. 输出整体 summary、简洁 tips，以及 {day_count} 天的 daily draft。
2. 每天只给一个主要景点、一个餐饮建议和一条当天备注。
3. day_index 必须从 1 到 {day_count}，且只能引用【{request.destination}】的信息。
4. 明确的额外备注必须在 days 中体现；轻松节奏应避免过满或过早出发。
5. 只返回 JSON 对象。

JSON 结构示例：
{{
  "summary": "整体概述",
  "tips": ["提示1", "提示2"],
  "days": [
    {{
      "day_index": 1,
      "theme": "当天主题",
      "spot_name": "主要景点",
      "spot_description": "景点推荐理由",
      "meal_name": "餐饮名称",
      "meal_notes": "餐饮说明",
      "daily_note": "当天备注"
    }}
  ]
}}
"""
    return [("system", SYSTEM_PROMPT), ("human", human_prompt)]
