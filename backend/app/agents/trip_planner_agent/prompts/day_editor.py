"""Single-day itinerary editing prompt templates."""

import json

from app.models.schemas import DayPlan, TripEditRequest


SYSTEM_PROMPT = (
    "你是一名旅行行程编辑助手。"
    "请根据用户编辑指令，只重写目标那一天的核心安排。"
    "你必须只输出一个 JSON 对象，不要输出 Markdown、解释文字或代码块。"
    "编辑结果要尽量保留原 itinerary 的整体风格、预算结构和轻松程度。"
)


def build_day_edit_messages(
    request: TripEditRequest,
    target_day: DayPlan,
) -> list[tuple[str, str]]:
    """Build messages for rewriting one itinerary day."""
    current_day_payload = {
        "day_index": target_day.day_index,
        "date": target_day.date.isoformat() if target_day.date else None,
        "theme": target_day.theme,
        "spots": [spot.model_dump(mode="json") for spot in target_day.spots],
        "meals": [meal.model_dump(mode="json") for meal in target_day.meals],
        "notes": list(target_day.notes),
    }
    itinerary_payload = request.current_itinerary.model_dump(mode="json")
    human_prompt = f"""
当前完整 itinerary：
{json.dumps(itinerary_payload, ensure_ascii=False, indent=2)}

需要重点编辑的目标 day：
{json.dumps(current_day_payload, ensure_ascii=False, indent=2)}

用户编辑指令：{request.user_instruction}
编辑范围：{request.edit_scope or '未指定'}
需要尽量保留的约束：{', '.join(request.preserve_constraints) if request.preserve_constraints else '无'}

要求：只输出目标日的 theme、spot_name、spot_description、meal_name、meal_notes、daily_note。
如果用户要求更轻松或不要太满，应减少固定景点压力。只返回 JSON 对象。
"""
    return [("system", SYSTEM_PROMPT), ("human", human_prompt)]
