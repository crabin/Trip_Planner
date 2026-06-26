from __future__ import annotations

import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any

from app.agents.trip_planner_agent.utils import response_content_to_text
from app.integrations.web_search import FallbackWebSearchAgency, TavilyResponse
from app.models.schemas import (
    ChatbotMessageRequest,
    ChatbotMessageResponse,
    ChatbotResearchStep,
    ChatbotSearchSource,
)

from ..prompts import RESEARCH_SUMMARY_SYSTEM_PROMPT
from ..state import IntentDecision
from ..utils import (
    MAX_SEARCH_RESULTS,
    build_research_steps,
    format_search_sources,
    summarize_research_without_llm,
)

RESEARCH_SUMMARY_TIMEOUT_SECONDS = 20


class ResearchNode:
    def __init__(self, *, llm: Any | None, search_agency: Any | None = None) -> None:
        self.llm = llm
        self.search_agency = search_agency

    def _get_search_agency(self) -> Any:
        if self.search_agency is None:
            self.search_agency = FallbackWebSearchAgency()
        return self.search_agency

    def run(
        self,
        request: ChatbotMessageRequest,
        decision: IntentDecision,
    ) -> ChatbotMessageResponse:
        final_response: ChatbotMessageResponse | None = None
        for event in self.stream(request, decision):
            if event["event"] == "final":
                final_response = event["data"]
        if final_response is None:
            raise RuntimeError("Research stream finished without a final response.")
        return final_response

    def stream(
        self,
        request: ChatbotMessageRequest,
        decision: IntentDecision,
    ) -> Iterator[dict[str, Any]]:
        steps = self._build_steps(request, decision)
        all_sources: list[ChatbotSearchSource] = []
        yield {"event": "research_plan", "data": steps}

        for index, step in enumerate(steps):
            if step.query is None:
                steps[index] = step.model_copy(
                    update={
                        "status": "completed",
                        "summary": step.summary or "已完成需求理解。",
                    }
                )
                yield {"event": "research_step", "data": steps[index]}
                continue

            running_step = step.model_copy(update={"status": "running"})
            steps[index] = running_step
            yield {"event": "research_step", "data": running_step}

            try:
                response = self._get_search_agency().basic_search_news(
                    step.query,
                    max_results=MAX_SEARCH_RESULTS,
                )
            except Exception as exc:
                steps[index] = step.model_copy(
                    update={
                        "status": "failed",
                        "summary": f"该项暂时无法查证：{exc}",
                        "sources": [],
                    }
                )
                yield {"event": "research_step", "data": steps[index]}
                continue

            sources = format_search_sources(response)
            all_sources.extend(sources)
            steps[index] = step.model_copy(
                update={
                    "status": "completed",
                    "summary": self._summarize_step(response),
                    "sources": sources,
                }
            )
            yield {"event": "research_step", "data": steps[index]}

        reply = self._summarize_research(request, decision, steps)
        yield {
            "event": "final",
            "data": ChatbotMessageResponse(
                intent=decision.intent,
                reply=reply,
                reason=decision.reason,
                sources=all_sources[:MAX_SEARCH_RESULTS],
                research_steps=steps,
            ),
        }

    def _build_steps(
        self,
        request: ChatbotMessageRequest,
        decision: IntentDecision,
    ) -> list[ChatbotResearchStep]:
        return build_research_steps(request, decision)

    def _summarize_step(self, response: TavilyResponse) -> str:
        if not response.results:
            return "没有找到足够可靠的结果，建议换更具体的日期、景点或交通方式再查。"
        first = response.results[0]
        content = first.content.strip()
        if len(content) > 80:
            content = f"{content[:80]}..."
        return f"{first.title or '搜索结果'}：{content}"

    def _summarize_research(
        self,
        request: ChatbotMessageRequest,
        decision: IntentDecision,
        steps: list[ChatbotResearchStep],
    ) -> str:
        if self.llm is not None:
            try:
                response = _invoke_with_timeout(
                    self.llm,
                    [
                        ("system", RESEARCH_SUMMARY_SYSTEM_PROMPT),
                        (
                            "human",
                            json.dumps(
                                {
                                    "question": request.message,
                                    "intent": decision.intent,
                                    "answer_strategy": decision.answer_strategy,
                                    "generation_tasks": decision.generation_tasks,
                                    "itinerary_destination": (
                                        request.current_itinerary.destination
                                        if request.current_itinerary is not None
                                        else None
                                    ),
                                    "steps": [step.model_dump() for step in steps],
                                },
                                ensure_ascii=False,
                            ),
                        ),
                    ],
                )
                text = response_content_to_text(response).strip()
                if text:
                    return text
            except (Exception, TimeoutError):
                pass

        return summarize_research_without_llm(request, steps)


def _invoke_with_timeout(llm: Any, messages: list[tuple[str, str]]) -> Any:
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(llm.invoke, messages)
    try:
        return future.result(timeout=RESEARCH_SUMMARY_TIMEOUT_SECONDS)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
