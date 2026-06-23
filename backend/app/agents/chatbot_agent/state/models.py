from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ChatIntent = Literal["ask", "update", "search"]


@dataclass(frozen=True)
class IntentDecision:
    intent: ChatIntent
    reason: str
    search_query: str | None = None
    edit_scope: str | None = None

