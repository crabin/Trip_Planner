from app.agents.destination_intelligence_agent.tools.search import TavilyNewsAgency
from app.agents.destination_intelligence_agent.utils.retry_helper import (
    RetryConfig,
    with_graceful_retry,
)
from app.services.web_search_service import TavilyNewsAgency as SharedTavilyNewsAgency


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
