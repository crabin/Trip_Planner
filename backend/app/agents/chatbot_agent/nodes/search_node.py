from __future__ import annotations

import json
from typing import Any

from app.agents.trip_planner_agent.utils import response_content_to_text
from app.integrations.web_search import FallbackWebSearchAgency, TavilyResponse
from app.models.schemas import ChatbotMessageRequest, ChatbotMessageResponse

from ..prompts import SEARCH_SUMMARY_SYSTEM_PROMPT
from ..state import IntentDecision
from ..utils import MAX_SEARCH_RESULTS, format_search_sources


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

    def run(
        self,
        request: ChatbotMessageRequest,
        decision: IntentDecision,
    ) -> ChatbotMessageResponse:
        query = decision.search_query or request.message
        try:
            search_response = self._get_search_agency().basic_search_news(
                query,
                max_results=MAX_SEARCH_RESULTS,
            )
        except Exception as exc:
            return ChatbotMessageResponse(
                intent="search",
                reply=f"我理解这是需要联网查询的问题，但当前搜索服务不可用：{exc}",
                reason=decision.reason,
            )

        reply = self._summarize_search_answer(request.message, search_response)
        return ChatbotMessageResponse(
            intent="search",
            reply=reply,
            reason=decision.reason,
            sources=format_search_sources(search_response),
        )

    def _summarize_search_answer(self, message: str, response: TavilyResponse) -> str:
        if not response.results:
            return "我尝试联网查询了，但没有找到足够可靠的结果。可以换一个更具体的景点、日期或交通问题再查。"

        if self.llm is not None:
            try:
                llm_response = self.llm.invoke(
                    [
                        ("system", SEARCH_SUMMARY_SYSTEM_PROMPT),
                        (
                            "human",
                            json.dumps(
                                {
                                    "question": message,
                                    "results": [
                                        result.to_dict()
                                        for result in response.results[:MAX_SEARCH_RESULTS]
                                    ],
                                },
                                ensure_ascii=False,
                            ),
                        ),
                    ]
                )
                text = response_content_to_text(llm_response).strip()
                if text:
                    return text
            except Exception:
                pass

        bullets = []
        for result in response.results[:3]:
            snippet = result.content.strip()
            if len(snippet) > 90:
                snippet = f"{snippet[:90]}..."
            bullets.append(f"{result.title or '搜索结果'}：{snippet}")
        return "我查到这些线索：\n" + "\n".join(f"- {item}" for item in bullets)
