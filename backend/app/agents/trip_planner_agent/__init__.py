"""Trip-planner agent package and backward-compatible public API.

New code may import from the focused submodules. Existing callers can continue
to import this package exactly as they imported the former single-file module.
"""

from app.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MAX_RETRIES,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
)
from app.models.schemas import DayPlan, TripEditRequest, TripRequest

from . import agent as _agent
from .llms import LLMSettings, build_chat_llm
from .state import DayEditDraft, PlannerDayDraft, PlannerDraft
from .tools.rag_tool import get_destination_guide_context


def _current_settings() -> LLMSettings:
    """Read package attributes so legacy monkeypatch-based callers still work."""
    return LLMSettings(
        api_key=LLM_API_KEY,
        model=LLM_MODEL,
        base_url=LLM_BASE_URL,
        timeout_seconds=LLM_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
    )


def _build_chat_llm():
    """Compatibility alias for the former private model factory."""
    return build_chat_llm(_current_settings())


def collect_trip_context(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
    top_k: int = 5,
) -> list[str]:
    return _agent.collect_trip_context(
        destination,
        preferences,
        pace,
        special_notes,
        top_k,
        retriever=get_destination_guide_context,
    )


def generate_planner_draft(
    request: TripRequest,
    rag_contexts: list[str],
    day_count: int,
) -> PlannerDraft | None:
    return _agent.generate_planner_draft(
        request,
        rag_contexts,
        day_count,
        settings=_current_settings(),
    )


def generate_day_edit_draft(
    request: TripEditRequest,
    target_day: DayPlan,
) -> DayEditDraft | None:
    return _agent.generate_day_edit_draft(
        request,
        target_day,
        settings=_current_settings(),
    )


__all__ = [
    "DayEditDraft",
    "PlannerDayDraft",
    "PlannerDraft",
    "collect_trip_context",
    "generate_day_edit_draft",
    "generate_planner_draft",
]
