from app.agents.destination_intelligence_agent.tools.search import TavilyNewsAgency
from app.agents.destination_intelligence_agent.utils.retry_helper import (
    RetryConfig,
    with_graceful_retry,
)
from app.integrations.web_search import (
    FallbackWebSearchAgency,
    SearxngNewsAgency,
    TavilyNewsAgency as SharedTavilyNewsAgency,
    TavilyResponse,
)


def test_destination_search_reexports_shared_web_search_service() -> None:
    assert TavilyNewsAgency is SharedTavilyNewsAgency


def test_with_graceful_retry_returns_fallback_after_configured_attempts() -> None:
    attempts = 0
    fallback = object()

    @with_graceful_retry(
        RetryConfig(max_attempts=3, initial_delay=0),
        default_return=fallback,
    )
    def always_fails() -> object:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("temporary search failure")

    assert always_fails() is fallback
    assert attempts == 3


def test_with_graceful_retry_returns_successful_retry() -> None:
    attempts = 0

    @with_graceful_retry(RetryConfig(max_attempts=3, initial_delay=0))
    def succeeds_on_second_attempt() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary search failure")
        return "ok"

    assert succeeds_on_second_attempt() == "ok"
    assert attempts == 2


def test_search_normalizes_missing_provider_fields_to_strings() -> None:
    class FakeClient:
        def search(self, **kwargs):
            return {
                "query": None,
                "results": [
                    {
                        "title": None,
                        "url": None,
                        "content": None,
                        "raw_content": None,
                    }
                ],
            }

    agency = object.__new__(TavilyNewsAgency)
    agency._client = FakeClient()

    response = agency._search_internal(query="厦门旅行")

    assert response.query == "厦门旅行"
    assert response.results[0].title == ""
    assert response.results[0].url == ""
    assert response.results[0].content == ""


def test_searxng_search_normalizes_json_results(monkeypatch) -> None:
    class FakeElapsed:
        def total_seconds(self) -> float:
            return 0.12

    class FakeResponse:
        elapsed = FakeElapsed()

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "query": "大理旅行",
                "answers": ["适合安排洱海和古城。"],
                "results": [
                    {
                        "title": "大理三日游攻略",
                        "url": "https://example.com/dali",
                        "content": "洱海、古城、苍山可以组合安排。",
                        "score": 2,
                        "publishedDate": "2026-06-01",
                    }
                ],
            }

    def fake_get(url, *, params, timeout):
        assert url == "http://searxng.local/search"
        assert params["q"] == "大理旅行"
        assert params["format"] == "json"
        assert timeout == 30.0
        return FakeResponse()

    monkeypatch.setattr("app.integrations.web_search.httpx.get", fake_get)

    response = SearxngNewsAgency("http://searxng.local").basic_search_news("大理旅行")

    assert response.query == "大理旅行"
    assert response.answer == "适合安排洱海和古城。"
    assert response.results[0].title == "大理三日游攻略"
    assert response.results[0].url == "https://example.com/dali"
    assert response.results[0].content == "洱海、古城、苍山可以组合安排。"
    assert response.results[0].score == 2.0
    assert response.results[0].published_date == "2026-06-01"


def test_fallback_search_uses_secondary_engine_after_primary_failure() -> None:
    class FailingSearch:
        def basic_search_news(self, query: str, max_results: int = 7) -> TavilyResponse:
            return TavilyResponse(query="搜索失败")

    class WorkingSearch:
        def basic_search_news(self, query: str, max_results: int = 7) -> TavilyResponse:
            return TavilyResponse(query=query)

    agency = FallbackWebSearchAgency(primary_engine="searxng")
    agency._clients = {
        "searxng": FailingSearch(),
        "tavily": WorkingSearch(),
    }

    assert agency.basic_search_news("大理旅行").query == "大理旅行"
