from __future__ import annotations

import re
from typing import Any

from app.models.schemas import Itinerary

from ..state import IntentDecision

UPDATE_TERMS = (
    "改",
    "调整",
    "更新",
    "替换",
    "删除",
    "增加",
    "不要",
    "换成",
    "安排",
    "移到",
)
SEARCH_TERMS = (
    "查",
    "搜索",
    "联网",
    "最新",
    "现在",
    "今天",
    "开放",
    "营业",
    "门票",
    "天气",
    "交通",
    "是否",
)
RESULT_PAGE_TERMS = (
    "结果页",
    "行程",
    "第",
    "天",
    "预算",
    "酒店",
    "餐厅",
    "景点",
)


def compact_itinerary(itinerary: Itinerary | None) -> dict[str, Any]:
    if itinerary is None:
        return {}

    return {
        "trip_id": itinerary.trip_id,
        "destination": itinerary.destination,
        "summary": itinerary.summary,
        "estimated_budget": itinerary.estimated_budget,
        "days": [
            {
                "day_index": day.day_index,
                "date": day.date.isoformat() if day.date else None,
                "theme": day.theme,
                "spots": [spot.name for spot in day.spots],
                "meals": [meal.name for meal in day.meals],
                "hotel": day.hotel.name if day.hotel else None,
                "notes": day.notes[:3],
            }
            for day in itinerary.days
        ],
    }


def guess_day_scope(text: str) -> str | None:
    match = re.search(r"第\s*(\d+)\s*天|D\s*(\d+)", text, flags=re.IGNORECASE)
    if not match:
        return None
    value = match.group(1) or match.group(2)
    return f"day_{value}"


def fallback_decision(message: str, itinerary: Itinerary | None) -> IntentDecision:
    text = message.strip()
    has_itinerary_context = itinerary is not None
    contains_update = any(term in text for term in UPDATE_TERMS)
    contains_search = any(term in text for term in SEARCH_TERMS)
    contains_result_page = any(term in text for term in RESULT_PAGE_TERMS)

    if has_itinerary_context and contains_update and contains_result_page:
        return IntentDecision(
            intent="update",
            reason="用户在当前行程上下文中提出修改要求。",
            edit_scope=guess_day_scope(text),
        )

    if contains_search:
        destination = itinerary.destination if itinerary else ""
        query = f"{destination} {text}".strip()
        return IntentDecision(
            intent="search",
            reason="用户要求查询新的或时效性内容。",
            search_query=query,
        )

    return IntentDecision(
        intent="ask",
        reason="用户是在询问当前规划或寻求使用帮助。",
    )

