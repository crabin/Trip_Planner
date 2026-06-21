"""Travel-guide context collection node."""

from collections.abc import Callable

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
    return retriever(
        destination=destination,
        preferences=preferences,
        pace=pace,
        special_notes=special_notes,
        top_k=top_k,
    )
