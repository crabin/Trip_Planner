"""Deprecated import path for shared web search integrations.

New code should import from :mod:`app.integrations.web_search`. This module is
kept so existing agents, scripts, and tests continue to work while the backend
is reorganized by responsibility.
"""

from app.integrations.web_search import (
    FallbackWebSearchAgency,
    ImageResult,
    SearchEngine,
    SearchResult,
    SearxngNewsAgency,
    TavilyNewsAgency,
    TavilyResponse,
)

__all__ = [
    "FallbackWebSearchAgency",
    "ImageResult",
    "SearchEngine",
    "SearchResult",
    "SearxngNewsAgency",
    "TavilyNewsAgency",
    "TavilyResponse",
]
