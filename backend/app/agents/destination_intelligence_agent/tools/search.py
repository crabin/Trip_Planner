"""Backward-compatible web search tools for destination intelligence.

The shared implementation lives in :mod:`app.services.web_search_service` so
other agents, including the floating chatbot agent, can use the same Tavily
normalization and retry behavior.
"""

from app.services.web_search_service import (
    ImageResult,
    SearchResult,
    TavilyNewsAgency,
    TavilyResponse,
)

__all__ = [
    "ImageResult",
    "SearchResult",
    "TavilyNewsAgency",
    "TavilyResponse",
]
