from __future__ import annotations

import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any

from loguru import logger

from app.agents.trip_planner_agent.utils import response_content_to_text
from app.config import LLM_TIMEOUT_SECONDS
from app.integrations.web_search import FallbackWebSearchAgency, TavilyResponse
from app.models.schemas import (
    ChatbotMessageRequest,
    ChatbotMessageResponse,
    ChatbotResearchStep,
    ChatbotSearchSource,
)

from ..prompts import RESEARCH_COMPACT_SUMMARY_SYSTEM_PROMPT
from ..state import IntentDecision
from ..utils import (
    MAX_SEARCH_RESULTS,
    build_research_steps,
    format_search_sources,
    summarize_research_without_llm,
)

RESEARCH_SUMMARY_TIMEOUT_SECONDS = LLM_TIMEOUT_SECONDS
SUMMARY_EVIDENCE_SOURCE_LIMIT = 2
SUMMARY_EVIDENCE_CONTENT_LIMIT = 500


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
        yield {"event": "research_plan", "data": list(steps)}

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

        synthesis_step = ChatbotResearchStep(
            id="synthesize",
            title="整理最终回答",
            status="running",
            summary=build_synthesis_summary(decision),
        )
        steps.append(synthesis_step)
        yield {"event": "research_step", "data": synthesis_step}

        reply = self._summarize_research(request, decision, steps)
        steps[-1] = synthesis_step.model_copy(
            update={
                "status": "completed",
                "summary": "已根据完成的查询结果整理最终建议。",
            }
        )
        yield {"event": "research_step", "data": steps[-1]}
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
        log_context = _research_summary_log_context(request)
        if self.llm is None:
            logger.warning(
                "Research summary LLM is unavailable; using non-LLM fallback: {}",
                log_context,
            )
            return summarize_research_without_llm(request, steps)

        try:
            response = _invoke_with_timeout(
                self.llm,
                [
                    ("system", RESEARCH_COMPACT_SUMMARY_SYSTEM_PROMPT),
                    (
                        "human",
                        json.dumps(
                            build_compact_summary_payload(request, decision, steps),
                            ensure_ascii=False,
                        ),
                    ),
                ],
            )
            text = response_content_to_text(response).strip()
            if text:
                return text
            logger.warning(
                "Research summary LLM returned empty response: {}",
                log_context,
            )
        except TimeoutError:
            logger.warning(
                "Research summary LLM timed out after {} seconds; using non-LLM fallback: {}",
                RESEARCH_SUMMARY_TIMEOUT_SECONDS,
                log_context,
            )
            return summarize_research_without_llm(request, steps)
        except Exception:
            logger.exception(
                "Research summary LLM failed: {}",
                log_context,
            )

        logger.warning(
            "Research summary LLM failed or returned empty response; using non-LLM fallback: {}",
            log_context,
        )
        return summarize_research_without_llm(request, steps)


def _research_summary_log_context(request: ChatbotMessageRequest) -> dict[str, object]:
    return {
        "message_length": len(request.message),
        "has_current_itinerary": request.current_itinerary is not None,
        "history_count": len(request.history),
        "has_conversation_summary": bool(request.conversation_summary),
    }


def _invoke_with_timeout(llm: Any, messages: list[tuple[str, str]]) -> Any:
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(llm.invoke, messages)
    try:
        return future.result(timeout=RESEARCH_SUMMARY_TIMEOUT_SECONDS)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def build_synthesis_summary(decision: IntentDecision) -> str:
    if decision.generation_tasks:
        return "；".join(decision.generation_tasks[:3])
    if decision.answer_strategy:
        return decision.answer_strategy
    return "结合已完成的查询记录，生成贴合用户问题的回答。"


def build_source_evidence(steps: list[ChatbotResearchStep]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for step in steps:
        if not step.query or step.status != "completed":
            continue
        evidence.append(
            {
                "title": step.title,
                "query": step.query,
                "summary": step.summary,
                "sources": [
                    {
                        "title": source.title,
                        "url": source.url,
                        "content": _truncate_text(source.content, SUMMARY_EVIDENCE_CONTENT_LIMIT),
                        "published_date": source.published_date,
                    }
                    for source in step.sources[:SUMMARY_EVIDENCE_SOURCE_LIMIT]
                ],
            }
        )
    return evidence


def build_compact_summary_payload(
    request: ChatbotMessageRequest,
    decision: IntentDecision,
    steps: list[ChatbotResearchStep],
) -> dict[str, Any]:
    return {
        "question": request.message,
        "intent": decision.intent,
        "answer_strategy": decision.answer_strategy,
        "generation_tasks": decision.generation_tasks,
        "traveler_profile": request.profile.model_dump(),
        "conversation_summary": request.conversation_summary,
        "itinerary_destination": (
            request.current_itinerary.destination
            if request.current_itinerary is not None
            else None
        ),
        "source_evidence": [
            {
                "query": item["query"],
                "summary": item["summary"],
                "sources": item["sources"],
            }
            for item in build_source_evidence(steps)
        ],
    }


def _truncate_text(value: str, max_length: int) -> str:
    text = " ".join(value.split())
    if len(text) <= max_length:
        return text
    return f"{text[:max_length].rstrip()}..."
