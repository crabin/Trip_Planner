from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from app.integrations.web_search import FallbackWebSearchAgency
from app.models.schemas import ChatbotMessageRequest, ChatbotMessageResponse

from .realtime_query import RealtimeQueryRouter
from ..state import IntentDecision


class SearchNode:
    def __init__(
        self,
        *,
        llm: Any | None,
        search_agency: FallbackWebSearchAgency | None = None,
    ) -> None:
        self.llm = llm
        self.search_agency = search_agency

    def _get_search_agency(self) -> FallbackWebSearchAgency:
        if self.search_agency is None:
            self.search_agency = FallbackWebSearchAgency()
        return self.search_agency

    def _get_realtime_router(self) -> RealtimeQueryRouter:
        return RealtimeQueryRouter(llm=self.llm, search_agency=self._get_search_agency())

    def run(
        self,
        request: ChatbotMessageRequest,
        decision: IntentDecision,
    ) -> ChatbotMessageResponse:
        return self._get_realtime_router().run(request, decision).response

    def stream(
        self,
        request: ChatbotMessageRequest,
        decision: IntentDecision,
    ) -> Iterator[dict[str, Any]]:
        yield from self._get_realtime_router().stream(request, decision)
