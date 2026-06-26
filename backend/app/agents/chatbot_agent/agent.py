from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from app.integrations.web_search import FallbackWebSearchAgency
from app.models.schemas import ChatbotMessageRequest, ChatbotMessageResponse
from app.services.trip_service import edit_trip_itinerary

from .graph import build_chatbot_graph, stream_chatbot_graph
from .llms import build_chat_llm
from .nodes import AskNode, IntentClassificationNode, ResearchNode, SearchNode, UpdateNode
from .state import IntentDecision


class ChatbotAgent:
    """Agent for the floating ChatUI bot."""

    def __init__(
        self,
        *,
        llm: Any | None = None,
        search_agency: FallbackWebSearchAgency | None = None,
    ) -> None:
        self.llm = llm if llm is not None else build_chat_llm()
        self.intent_node = IntentClassificationNode(self.llm)
        self.ask_node = AskNode()
        self.update_node = UpdateNode(edit_trip_itinerary)
        self.search_node = SearchNode(llm=self.llm, search_agency=search_agency)
        self.research_node = ResearchNode(llm=self.llm, search_agency=search_agency)
        self.graph = build_chatbot_graph(self)

    @property
    def search_agency(self) -> FallbackWebSearchAgency | None:
        return self.search_node.search_agency

    @search_agency.setter
    def search_agency(self, value: FallbackWebSearchAgency | None) -> None:
        self.search_node.search_agency = value
        self.research_node.search_agency = value

    def classify_intent(self, request: ChatbotMessageRequest) -> IntentDecision:
        return self.intent_node.run(request)

    def handle(self, request: ChatbotMessageRequest) -> ChatbotMessageResponse:
        result = self.graph.invoke({"request": request, "events": []})
        return result["response"]

    def stream(self, request: ChatbotMessageRequest) -> Iterator[dict[str, Any]]:
        yield from stream_chatbot_graph(self, request)


def handle_chatbot_message(request: ChatbotMessageRequest) -> ChatbotMessageResponse:
    return ChatbotAgent().handle(request)
