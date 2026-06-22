from pathlib import Path
import runpy
import subprocess
import sys
from types import ModuleType


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
