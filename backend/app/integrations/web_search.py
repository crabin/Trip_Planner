from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal, Optional
from urllib.parse import urljoin

import httpx
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


SearchEngine = Literal["tavily", "searxng"]
DEFAULT_SEARXNG_BASE_URL = "http://lpbkuaile6:8888/"


def _is_failed_response(response: TavilyResponse) -> bool:
    return response.query == "搜索失败"


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


class SearxngNewsAgency:
    """SearXNG-backed client that normalizes JSON results to TavilyResponse."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 30.0,
    ) -> None:
        resolved_base_url = base_url or os.getenv("SEARXNG_BASE_URL") or DEFAULT_SEARXNG_BASE_URL
        self.base_url = resolved_base_url.rstrip("/") + "/"
        self.timeout = timeout

    @with_graceful_retry(SEARCH_API_RETRY_CONFIG, default_return=TavilyResponse(query="搜索失败"))
    def _search_internal(
        self,
        *,
        query: str,
        max_results: int = 10,
        categories: str | None = None,
        time_range: str | None = None,
    ) -> TavilyResponse:
        params: dict[str, object] = {
            "q": query,
            "format": "json",
            "safesearch": 1,
        }
        if categories:
            params["categories"] = categories
        if time_range:
            params["time_range"] = time_range

        endpoint = urljoin(self.base_url, "search")
        response = httpx.get(endpoint, params=params, timeout=self.timeout)
        response.raise_for_status()
        response_dict = response.json()

        raw_results = response_dict.get("results") or []
        search_results = [
            self._normalize_result(item)
            for item in raw_results[:max_results]
            if isinstance(item, dict)
        ]
        image_results = [
            ImageResult(
                url=str(item.get("img_src") or item.get("thumbnail") or item.get("url") or ""),
                description=item.get("content") or item.get("title"),
            )
            for item in raw_results[:max_results]
            if isinstance(item, dict) and (item.get("img_src") or item.get("thumbnail"))
        ]

        return TavilyResponse(
            query=str(response_dict.get("query") or query),
            answer=self._extract_answer(response_dict),
            results=search_results,
            images=image_results,
            response_time=response.elapsed.total_seconds(),
        )

    def _normalize_result(self, item: dict[str, object]) -> SearchResult:
        content = item.get("content") or item.get("snippet") or ""
        score = item.get("score")
        numeric_score = score if isinstance(score, int | float) else None
        return SearchResult(
            title=str(item.get("title") or ""),
            url=str(item.get("url") or item.get("img_src") or ""),
            content=str(content),
            score=float(numeric_score) if numeric_score is not None else None,
            raw_content=str(content) if content else None,
            published_date=self._string_or_none(
                item.get("publishedDate") or item.get("published_date") or item.get("date")
            ),
        )

    def _extract_answer(self, response_dict: dict[str, object]) -> str | None:
        answers = response_dict.get("answers")
        if isinstance(answers, list) and answers:
            return "\n".join(str(answer) for answer in answers if answer)
        return None

    def _string_or_none(self, value: object) -> str | None:
        if value is None:
            return None
        return str(value)

    def basic_search_news(self, query: str, max_results: int = 7) -> TavilyResponse:
        logger.info("TOOL: SearXNG 基础网页搜索 (query: {})", query)
        return self._search_internal(query=query, max_results=max_results)

    def deep_search_news(self, query: str) -> TavilyResponse:
        logger.info("TOOL: SearXNG 深度网页研究 (query: {})", query)
        return self._search_internal(query=query, max_results=20)

    def search_news_last_24_hours(self, query: str) -> TavilyResponse:
        logger.info("TOOL: SearXNG 搜索24小时内信息 (query: {})", query)
        return self._search_internal(query=query, time_range="day", max_results=10)

    def search_news_last_week(self, query: str) -> TavilyResponse:
        logger.info("TOOL: SearXNG 搜索本月信息兜底本周需求 (query: {})", query)
        return self._search_internal(query=query, time_range="month", max_results=10)

    def search_images_for_news(self, query: str) -> TavilyResponse:
        logger.info("TOOL: SearXNG 查找目的地图片 (query: {})", query)
        return self._search_internal(query=query, categories="images", max_results=5)

    def search_news_by_date(self, query: str, start_date: str, end_date: str) -> TavilyResponse:
        logger.info(
            "TOOL: SearXNG 按日期搜索降级为普通搜索 (query: {}, from: {}, to: {})",
            query,
            start_date,
            end_date,
        )
        return self._search_internal(query=query, max_results=15)


class FallbackWebSearchAgency:
    """Select Tavily or SearXNG first and fall back to the other after retries."""

    def __init__(
        self,
        *,
        primary_engine: SearchEngine = "tavily",
        tavily_api_key: str | None = None,
        searxng_base_url: str | None = None,
    ) -> None:
        self.primary_engine = primary_engine
        self.tavily_api_key = tavily_api_key
        self.searxng_base_url = searxng_base_url
        self._clients: dict[SearchEngine, TavilyNewsAgency | SearxngNewsAgency] = {}

    def _ordered_engines(self) -> list[SearchEngine]:
        fallback: SearchEngine = "searxng" if self.primary_engine == "tavily" else "tavily"
        return [self.primary_engine, fallback]

    def _get_client(self, engine: SearchEngine) -> TavilyNewsAgency | SearxngNewsAgency:
        if engine not in self._clients:
            if engine == "tavily":
                self._clients[engine] = TavilyNewsAgency(api_key=self.tavily_api_key)
            else:
                self._clients[engine] = SearxngNewsAgency(base_url=self.searxng_base_url)
        return self._clients[engine]

    def _call(self, method_name: str, *args, **kwargs) -> TavilyResponse:
        last_response: TavilyResponse | None = None
        for engine in self._ordered_engines():
            try:
                client = self._get_client(engine)
                response = getattr(client, method_name)(*args, **kwargs)
            except Exception as exc:
                logger.warning("{} 搜索不可用，准备尝试兜底服务: {}", engine, exc)
                continue

            last_response = response
            if not _is_failed_response(response):
                if engine != self.primary_engine:
                    logger.info("已使用 {} 完成搜索兜底", engine)
                return response
            logger.warning("{} 搜索重试后仍失败，准备尝试兜底服务", engine)

        return last_response or TavilyResponse(query="搜索失败")

    def basic_search_news(self, query: str, max_results: int = 7) -> TavilyResponse:
        return self._call("basic_search_news", query, max_results)

    def deep_search_news(self, query: str) -> TavilyResponse:
        return self._call("deep_search_news", query)

    def search_news_last_24_hours(self, query: str) -> TavilyResponse:
        return self._call("search_news_last_24_hours", query)

    def search_news_last_week(self, query: str) -> TavilyResponse:
        return self._call("search_news_last_week", query)

    def search_images_for_news(self, query: str) -> TavilyResponse:
        return self._call("search_images_for_news", query)

    def search_news_by_date(self, query: str, start_date: str, end_date: str) -> TavilyResponse:
        return self._call("search_news_by_date", query, start_date, end_date)


__all__ = [
    "FallbackWebSearchAgency",
    "ImageResult",
    "SearchResult",
    "SearxngNewsAgency",
    "SearchEngine",
    "TavilyNewsAgency",
    "TavilyResponse",
]
