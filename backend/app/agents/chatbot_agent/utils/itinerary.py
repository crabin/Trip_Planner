from __future__ import annotations

import re
from typing import Any

from app.models.schemas import Itinerary

from ..state import IntentDecision


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
    edit_scope = guess_day_scope(message) if itinerary is not None else None
    return IntentDecision(
        intent="clarify" if itinerary is None else "ask",
        reason="LLM 意图分类不可用或返回无效结果，未使用关键词规则做业务路由。",
        answer_strategy=(
            "信息不足，先请用户补充目的地、日期、人数、预算和偏好。"
            if itinerary is None
            else "围绕当前结果页行程回答，不触发联网查询或行程修改。"
        ),
        edit_scope=edit_scope,
        missing_slots=[] if itinerary is not None else ["destination", "date", "people", "budget", "preferences"],
    )
