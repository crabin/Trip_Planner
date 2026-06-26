from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ChatIntent = Literal[
    "ask",
    "update",
    "search",
    "research",
    "clarify",
    "risk_check",
    "compare",
    "personalize",
]


@dataclass(frozen=True)
class IntentDecision:
    intent: ChatIntent
    reason: str
    answer_strategy: str | None = None
    search_query: str | None = None
    edit_scope: str | None = None
    research_topics: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    generation_tasks: list[str] = field(default_factory=list)
    missing_slots: list[str] = field(default_factory=list)
