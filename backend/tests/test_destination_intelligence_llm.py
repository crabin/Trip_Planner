from pathlib import Path
import runpy
import subprocess
import sys
from types import ModuleType

import httpx
from openai import APIError, BadRequestError


BASE_FILE = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "agents"
    / "destination_intelligence_agent"
    / "llms"
    / "base.py"
)


def test_base_can_load_without_package_context() -> None:
    namespace = runpy.run_path(str(BASE_FILE), run_name="base_smoke_test")

    assert "LLMClient" in namespace


def test_base_runs_as_a_standalone_script() -> None:
    result = subprocess.run(
        [sys.executable, str(BASE_FILE)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_client_uses_project_llm_request_settings(monkeypatch) -> None:
    namespace = runpy.run_path(str(BASE_FILE), run_name="base_config_test")
    llm_client = namespace["LLMClient"]
    config = namespace["config"]
    captured: dict[str, object] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    fake_module = ModuleType("langchain_openai")
    fake_module.ChatOpenAI = FakeChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)
    monkeypatch.setattr(config, "LLM_TIMEOUT_SECONDS", 42)
    monkeypatch.setattr(config, "LLM_MAX_RETRIES", 3)

    client = llm_client("test-key", "test-model", "https://example.com/v1")

    assert client.timeout == 42.0
    assert captured["timeout"] == 42.0
    assert captured["max_retries"] == 3


def test_stream_to_string_retries_error_raised_during_iteration() -> None:
    namespace = runpy.run_path(str(BASE_FILE), run_name="base_stream_retry_test")
    llm_client = namespace["LLMClient"]

    class Chunk:
        def __init__(self, content: str) -> None:
            self.content = content

    class FlakyStreamingClient:
        def __init__(self) -> None:
            self.calls = 0

        def stream(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                yield Chunk("")
                raise APIError(
                    "Upstream service temporarily unavailable",
                    request=httpx.Request("POST", "https://example.com/v1/chat"),
                    body=None,
                )
            yield Chunk("完整")
            yield Chunk("响应")

    client = llm_client.__new__(llm_client)
    client.client = FlakyStreamingClient()
    client.timeout = 60.0
    client.max_retries = 1
    client.retry_delay = 0

    result = client.stream_invoke_to_string("system", "user")

    assert result == "完整响应"
    assert client.client.calls == 2


def test_stream_retry_does_not_retry_bad_requests() -> None:
    namespace = runpy.run_path(str(BASE_FILE), run_name="base_stream_error_test")
    llm_client = namespace["LLMClient"]
    request = httpx.Request("POST", "https://example.com/v1/chat")
    response = httpx.Response(400, request=request)
    error = BadRequestError("invalid request", response=response, body=None)

    assert not llm_client._is_retryable_stream_error(error)
