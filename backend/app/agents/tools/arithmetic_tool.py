"""Deprecated import path; use trip_planner_agent.tools.arithmetic_tool."""

from app.agents.trip_planner_agent.tools.arithmetic_tool import (
    arithmetic_add,
    arithmetic_divide,
    arithmetic_multiply,
    arithmetic_subtract,
    calculate_budget_breakdown_with_tools,
)

__all__ = [
    "arithmetic_add",
    "arithmetic_divide",
    "arithmetic_multiply",
    "arithmetic_subtract",
    "calculate_budget_breakdown_with_tools",
]
