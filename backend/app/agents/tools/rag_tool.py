"""Deprecated import path; use trip_planner_agent.tools.rag_tool."""

from app.agents.trip_planner_agent.tools.rag_tool import (
    _build_destination_query,
    build_destination_query,
    get_destination_guide_context,
)

__all__ = [
    "_build_destination_query",
    "build_destination_query",
    "get_destination_guide_context",
]
