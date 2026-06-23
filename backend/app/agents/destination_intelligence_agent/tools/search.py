"""Backward-compatible web search tools for destination intelligence.

The shared implementation lives in :mod:`app.integrations.web_search` so
other agents, including the floating chatbot agent, can use the same Tavily
normalization and retry behavior.
"""

from app.integrations.web_search import (
    FallbackWebSearchAgency,
    ImageResult,
    SearchResult,
    SearxngNewsAgency,
    SearchEngine,
    TavilyNewsAgency,
    TavilyResponse,
)

__all__ = [
    "FallbackWebSearchAgency",
    "ImageResult",
    "SearchResult",
    "SearxngNewsAgency",
    "SearchEngine",
    "TavilyNewsAgency",
    "TavilyResponse",
]
