from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from app.services.retry_helper import (
    SEARCH_API_RETRY_CONFIG,
    with_graceful_retry,
)

try:
    from tavily import TavilyClient
except ImportError as exc:  # pragma: no cover - exercised only when optional dep is absent
    TavilyClient = None  # type: ignore[assignment]
    _TAVILY_IMPORT_ERROR: ImportError | None = exc
else:
    _TAVILY_IMPORT_ERROR = None


@dataclass
class SearchResult:
    """A normalized web search result shared by agents."""

    title: str
    url: str
    content: str
    score: Optional[float] = None
    raw_content: Optional[str] = None
    published_date: Optional[str] = None

    def to_dict(self) -> dict[str, object | None]:
        return {
            "title": self.title,
            "url": self.url,
            "content": self.content,
            "score": self.score,
            "raw_content": self.raw_content,
            "published_date": self.published_date,
        }


@dataclass
class ImageResult:
    """A normalized image search result."""

    url: str
    description: Optional[str] = None


@dataclass
class TavilyResponse:
    """Normalized Tavily response used across destination and chatbot agents."""

    query: str
    answer: Optional[str] = None
    results: list[SearchResult] = field(default_factory=list)
    images: list[ImageResult] = field(default_factory=list)
    response_time: Optional[float] = None


class TavilyNewsAgency:
    """Shared Tavily-backed web research client.

    The class and method names intentionally preserve the historical
    destination-intelligence API. New callers can treat them as general web
    research helpers.
    """

    def __init__(self, api_key: Optional[str] = None):
        if TavilyClient is None:
            raise ImportError("Tavily库未安装，请运行 `pip install tavily-python` 进行安装。") from _TAVILY_IMPORT_ERROR

        resolved_api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not resolved_api_key:
            raise ValueError("Tavily API Key未找到！请设置TAVILY_API_KEY环境变量或在初始化时提供")
        self._client = TavilyClient(api_key=resolved_api_key)

    @with_graceful_retry(SEARCH_API_RETRY_CONFIG, default_return=TavilyResponse(query="搜索失败"))
    def _search_internal(self, **kwargs) -> TavilyResponse:
        """Execute a normalized general-topic Tavily search."""
        try:
            kwargs["topic"] = "general"
            api_params = {key: value for key, value in kwargs.items() if value is not None}
            response_dict = self._client.search(**api_params)

            search_results = [
                SearchResult(
                    title=str(item.get("title") or ""),
                    url=str(item.get("url") or ""),
                    content=str(item.get("content") or ""),
                    score=item.get("score"),
                    raw_content=item.get("raw_content"),
                    published_date=item.get("published_date"),
                )
                for item in response_dict.get("results", [])
            ]
            image_results = [
                ImageResult(
                    url=str(item.get("url") or ""),
                    description=item.get("description"),
                )
                for item in response_dict.get("images", [])
            ]

            return TavilyResponse(
                query=str(response_dict.get("query") or kwargs.get("query") or ""),
                answer=response_dict.get("answer"),
                results=search_results,
                images=image_results,
                response_time=response_dict.get("response_time"),
            )
        except Exception:
            logger.exception("搜索时发生错误")
            raise

    def basic_search_news(self, query: str, max_results: int = 7) -> TavilyResponse:
        """Standard general web search. Historical method name kept for compatibility."""
        logger.info("TOOL: 基础网页搜索 (query: {})", query)
        return self._search_internal(
            query=query,
            max_results=max_results,
            search_depth="basic",
            include_answer=False,
        )

    def deep_search_news(self, query: str) -> TavilyResponse:
        """Advanced general web research. Historical method name kept for compatibility."""
        logger.info("TOOL: 深度网页研究 (query: {})", query)
        return self._search_internal(
            query=query,
            search_depth="advanced",
            max_results=20,
            include_answer="advanced",
        )

    def search_news_last_24_hours(self, query: str) -> TavilyResponse:
        logger.info("TOOL: 搜索24小时内信息 (query: {})", query)
        return self._search_internal(query=query, time_range="d", max_results=10)

    def search_news_last_week(self, query: str) -> TavilyResponse:
        logger.info("TOOL: 搜索本周信息 (query: {})", query)
        return self._search_internal(query=query, time_range="w", max_results=10)

    def search_images_for_news(self, query: str) -> TavilyResponse:
        logger.info("TOOL: 查找目的地图片 (query: {})", query)
        return self._search_internal(
            query=query,
            include_images=True,
            include_image_descriptions=True,
            max_results=5,
        )

    def search_news_by_date(self, query: str, start_date: str, end_date: str) -> TavilyResponse:
        logger.info("TOOL: 按发布日期范围搜索信息 (query: {}, from: {}, to: {})", query, start_date, end_date)
        return self._search_internal(
            query=query,
            start_date=start_date,
            end_date=end_date,
            max_results=15,
        )


__all__ = [
    "ImageResult",
    "SearchResult",
    "TavilyNewsAgency",
    "TavilyResponse",
]
