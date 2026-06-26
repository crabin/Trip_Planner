from __future__ import annotations

import json
from typing import Any

from app.agents.trip_planner_agent.utils import extract_json_object, response_content_to_text
from app.models.schemas import ChatbotMessageRequest

from ..prompts import INTENT_CLASSIFIER_SYSTEM_PROMPT
from ..state import IntentDecision
from ..utils import compact_itinerary, fallback_decision


class IntentClassificationNode:
    def __init__(self, llm: Any | None) -> None:
        self.llm = llm

    def run(self, request: ChatbotMessageRequest) -> IntentDecision:
        fallback = fallback_decision(request.message, request.current_itinerary)
        if self.llm is None:
            return fallback

        messages = [
            ("system", INTENT_CLASSIFIER_SYSTEM_PROMPT),
            (
                "human",
                json.dumps(
                    {
                        "message": request.message,
                        "has_current_itinerary": request.current_itinerary is not None,
                        "itinerary": compact_itinerary(request.current_itinerary),
                        "history": [item.model_dump() for item in request.history[-6:]],
                    },
                    ensure_ascii=False,
                ),
            ),
        ]
        try:
            response = self.llm.invoke(messages)
            raw_text = response_content_to_text(response)
            json_text = extract_json_object(raw_text)
            if json_text is None:
                return fallback
            payload = json.loads(json_text)
            intent = payload.get("intent")
            if intent not in {"ask", "update", "search", "research", "clarify", "risk_check"}:
                return fallback
            return IntentDecision(
                intent=intent,
                reason=str(payload.get("reason") or fallback.reason),
                answer_strategy=payload.get("answer_strategy") or fallback.answer_strategy,
                search_query=payload.get("search_query") or fallback.search_query,
                edit_scope=payload.get("edit_scope") or fallback.edit_scope,
                research_topics=_string_list(payload.get("research_topics"), fallback.research_topics),
                search_queries=_string_list(payload.get("search_queries"), fallback.search_queries),
                generation_tasks=_string_list(
                    payload.get("generation_tasks"),
                    fallback.generation_tasks,
                ),
                missing_slots=_string_list(payload.get("missing_slots"), fallback.missing_slots),
            )
        except Exception:
            return fallback


def _string_list(value: object, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    return [str(item) for item in value if item]
