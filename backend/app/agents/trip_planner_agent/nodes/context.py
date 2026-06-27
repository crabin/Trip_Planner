"""Travel-guide context collection node."""

from collections.abc import Callable
import re

from app.agents.tools.transport_tool import search_train_tickets_for_agent
from ..tools.rag_tool import get_destination_guide_context

ContextRetriever = Callable[..., list[str]]


def collect_trip_context(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
    top_k: int = 5,
    *,
    retriever: ContextRetriever = get_destination_guide_context,
) -> list[str]:
    """Collect local guide fragments needed to generate an itinerary."""
    contexts = retriever(
        destination=destination,
        preferences=preferences,
        pace=pace,
        special_notes=special_notes,
        top_k=top_k,
    )
    train_context = _build_train_ticket_context(destination, special_notes)
    if train_context:
        contexts.append(train_context)
    return contexts


def _build_train_ticket_context(destination: str, special_notes: str | None) -> str:
    note = (special_notes or "").strip()
    if not _looks_like_train_ticket_query(note):
        return ""
    message = " ".join(part for part in (destination.strip(), note) if part)
    result = search_train_tickets_for_agent(message, search_query=note)
    if not result.available:
        reason = result.error_message or "实时铁路查询暂时不可用。"
        return f"铁路实时信息待确认：{reason}"
    return "\n".join(
        [
            "铁路实时信息（来自 12306 MCP，写入行程时需提示最终以 12306 官方页面为准）：",
            result.answer,
            *result.source_notes,
        ]
    )


def _looks_like_train_ticket_query(text: str) -> bool:
    if not text:
        return False
    has_train_word = any(word in text for word in ("高铁", "动车", "火车", "铁路", "车票"))
    has_route = re.search(r"[\u4e00-\u9fff]{2,10}(?:到|去|至)[\u4e00-\u9fff]{2,10}", text)
    has_date = re.search(r"20\d{2}-\d{1,2}-\d{1,2}", text) or any(
        word in text for word in ("今天", "明天", "明日", "后天")
    )
    has_time_window = any(word in text for word in ("上午", "早上", "中午", "下午", "晚上", "夜里")) or re.search(
        r"\d{1,2}(?::\d{2})?\s*[-到至~]\s*\d{1,2}(?::\d{2})?",
        text,
    )
    return bool(has_train_word and has_route and has_date and has_time_window)
