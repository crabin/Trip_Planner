"""LLM invocation and structured-output validation nodes."""

import json
from typing import Any

from ..state import DayEditDraft, PlannerDraft
from ..utils import extract_json_object, response_content_to_text


def _normalize_day_edit_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """兼容模型返回的扁平结构和 DayPlan 风格结构。"""
    if "spot_name" in payload and "meal_name" in payload and "daily_note" in payload:
        return payload

    normalized = dict(payload)
    spots = payload.get("spots")
    if isinstance(spots, list) and spots:
        first_spot = spots[0] or {}
        normalized.setdefault("spot_name", first_spot.get("name", ""))
        normalized.setdefault("spot_description", first_spot.get("description", ""))
    meals = payload.get("meals")
    if isinstance(meals, list) and meals:
        first_meal = meals[0] or {}
        normalized.setdefault("meal_name", first_meal.get("name", ""))
        normalized.setdefault("meal_notes", first_meal.get("notes", ""))
    notes = payload.get("notes")
    if isinstance(notes, list) and notes:
        normalized.setdefault("daily_note", notes[-1] or "")
    return normalized


def generate_trip_draft(llm: Any, messages: list[tuple[str, str]], day_count: int) -> PlannerDraft | None:
    """Invoke the model and validate a complete trip draft."""
    try:
        response = llm.invoke(messages)
    except Exception as exc:
        print(f"[trip_planner_agent] 大模型调用失败: {type(exc).__name__}: {exc}")
        return None

    raw_text = response_content_to_text(response)
    json_text = extract_json_object(raw_text)
    if json_text is None:
        print("[trip_planner_agent] 未能从模型返回中提取 JSON。")
        print(f"[trip_planner_agent] 原始返回预览: {raw_text[:300]}")
        return None
    try:
        result = PlannerDraft.model_validate(json.loads(json_text))
    except Exception as exc:
        print(f"[trip_planner_agent] JSON 解析失败: {type(exc).__name__}: {exc}")
        print(f"[trip_planner_agent] 原始返回预览: {raw_text[:300]}")
        return None
    if len(result.days) != day_count:
        print(
            "[trip_planner_agent] 结构化结果天数不匹配，"
            f"expected={day_count}, actual={len(result.days)}"
        )
        return None
    return result


def generate_day_edit(llm: Any, messages: list[tuple[str, str]]) -> DayEditDraft | None:
    """Invoke the model and validate a single-day edit."""
    try:
        response = llm.invoke(messages)
    except Exception as exc:
        print(f"[trip_planner_agent] 单日编辑调用失败: {type(exc).__name__}: {exc}")
        return None

    raw_text = response_content_to_text(response)
    json_text = extract_json_object(raw_text)
    if json_text is None:
        print("[trip_planner_agent] 未能从单日编辑结果中提取 JSON。")
        print(f"[trip_planner_agent] 原始返回预览: {raw_text[:300]}")
        return None
    try:
        payload = json.loads(json_text)
        if not isinstance(payload, dict):
            raise ValueError("单日编辑结果不是 JSON 对象。")
        return DayEditDraft.model_validate(_normalize_day_edit_payload(payload))
    except Exception as exc:
        print(f"[trip_planner_agent] 单日编辑 JSON 解析失败: {type(exc).__name__}: {exc}")
        print(f"[trip_planner_agent] 原始返回预览: {raw_text[:300]}")
        return None
