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
from .utils import extract_profile_patch, merge_profile, summarize_conversation


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
        self.ask_node = AskNode(self.llm)
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
        return self.intent_node.run(self._with_current_profile(request))

    def handle(self, request: ChatbotMessageRequest) -> ChatbotMessageResponse:
        working_request = self._with_current_profile(request)
        result = self.graph.invoke({"request": working_request, "events": []})
        return self._with_memory(working_request, result["response"])

    def stream(self, request: ChatbotMessageRequest) -> Iterator[dict[str, Any]]:
        working_request = self._with_current_profile(request)
        for event in stream_chatbot_graph(self, working_request):
            if event.get("event") == "final" and isinstance(event.get("data"), ChatbotMessageResponse):
                yield {**event, "data": self._with_memory(working_request, event["data"])}
                continue
            yield event

    def _with_current_profile(self, request: ChatbotMessageRequest) -> ChatbotMessageRequest:
        profile = merge_profile(request.profile, extract_profile_patch(request.message))
        return request.model_copy(update={"profile": profile})

    def _with_memory(
        self,
        request: ChatbotMessageRequest,
        response: ChatbotMessageResponse,
    ) -> ChatbotMessageResponse:
        profile = merge_profile(request.profile, extract_profile_patch(request.message))
        profile = merge_profile(profile, response.profile)
        summary = summarize_conversation(
            request.conversation_summary,
            request.history,
            request.message,
            response.reply,
        )
        return response.model_copy(
            update={
                "profile": profile,
                "conversation_summary": summary,
            }
        )


def handle_chatbot_message(request: ChatbotMessageRequest) -> ChatbotMessageResponse:
    return ChatbotAgent().handle(request)
