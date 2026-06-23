from __future__ import annotations

from app.models.schemas import ChatbotSearchSource
from app.services.web_search_service import TavilyResponse

MAX_SEARCH_RESULTS = 10


def format_search_sources(response: TavilyResponse) -> list[ChatbotSearchSource]:
    return [
        ChatbotSearchSource(
            title=result.title,
            url=result.url,
            content=result.content,
            raw_content=result.raw_content,
            published_date=result.published_date,
            score=result.score,
        )
        for result in response.results[:MAX_SEARCH_RESULTS]
    ]

