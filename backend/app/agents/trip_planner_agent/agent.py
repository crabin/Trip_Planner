"""Public orchestration logic for the trip-planner agent."""

from collections.abc import Callable
from typing import Any

from app.models.schemas import DayPlan, TripEditRequest, TripRequest

from .llms import LLMSettings, build_chat_llm
from .nodes.context import ContextRetriever, collect_trip_context as collect_context_node
from .nodes.generation import generate_day_edit, generate_trip_draft
from .prompts import build_day_edit_messages, build_planner_messages
from .state import DayEditDraft, PlannerDraft
from .tools.rag_tool import get_destination_guide_context

LLMFactory = Callable[[LLMSettings | None], Any | None]


def collect_trip_context(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
    top_k: int = 5,
    *,
    retriever: ContextRetriever = get_destination_guide_context,
) -> list[str]:
    """Collect the local guide context needed by downstream generation."""
    return collect_context_node(
        destination,
        preferences,
        pace,
        special_notes,
        top_k,
        retriever=retriever,
    )


def generate_planner_draft(
    request: TripRequest,
    rag_contexts: list[str],
    day_count: int,
    *,
    settings: LLMSettings | None = None,
    llm_factory: LLMFactory = build_chat_llm,
) -> PlannerDraft | None:
    """Generate a structured trip draft, returning ``None`` for fallback."""
    resolved = settings or LLMSettings.from_config()
    llm = llm_factory(resolved)
    if llm is None:
        return None
    print("[trip_planner_agent] 准备调用大模型...")
    print(f"[trip_planner_agent] model = {resolved.model}")
    print(f"[trip_planner_agent] base_url = {resolved.base_url or '<DEFAULT>'}")
    messages = build_planner_messages(request, rag_contexts, day_count)
    result = generate_trip_draft(llm, messages, day_count)
    if result is not None:
        print("[trip_planner_agent] 大模型调用完成。")
    return result


def generate_day_edit_draft(
    request: TripEditRequest,
    target_day: DayPlan,
    *,
    settings: LLMSettings | None = None,
    llm_factory: LLMFactory = build_chat_llm,
) -> DayEditDraft | None:
    """Generate a structured edit for one itinerary day."""
    resolved = settings or LLMSettings.from_config()
    llm = llm_factory(resolved)
    if llm is None:
        return None
    print("[trip_planner_agent] 准备调用大模型进行单日编辑...")
    print(f"[trip_planner_agent] model = {resolved.model}")
    messages = build_day_edit_messages(request, target_day)
    return generate_day_edit(llm, messages)


__all__ = [
    "collect_trip_context",
    "generate_day_edit_draft",
    "generate_planner_draft",
]
