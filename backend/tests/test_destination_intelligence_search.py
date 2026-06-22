from pathlib import Path
import runpy

from app.agents.destination_intelligence_agent.utils.retry_helper import (
    RetryConfig,
    with_graceful_retry,
)


def test_search_script_loads_without_importing_pypi_retry_helper() -> None:
    search_script = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "agents"
        / "destination_intelligence_agent"
        / "tools"
        / "search.py"
    )

    namespace = runpy.run_path(str(search_script), run_name="destination_search_test")

    assert namespace["with_graceful_retry"].__module__.endswith("utils.retry_helper")


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
