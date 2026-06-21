"""Chat-model configuration and factory."""

from dataclasses import dataclass
from typing import Any

from app import config


@dataclass(frozen=True)
class LLMSettings:
    """The small, explicit configuration surface needed by the agent."""

    api_key: str
    model: str
    base_url: str
    timeout_seconds: float
    max_retries: int
    temperature: float = 0.3

    @classmethod
    def from_config(cls) -> "LLMSettings":
        return cls(
            api_key=config.LLM_API_KEY,
            model=config.LLM_MODEL,
            base_url=config.LLM_BASE_URL,
            timeout_seconds=config.LLM_TIMEOUT_SECONDS,
            max_retries=config.LLM_MAX_RETRIES,
        )


def build_chat_llm(settings: LLMSettings | None = None) -> Any | None:
    """Create ChatOpenAI when credentials and the optional dependency exist."""
    resolved = settings or LLMSettings.from_config()
    if not resolved.api_key:
        return None

    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        return None

    return ChatOpenAI(
        model=resolved.model,
        temperature=resolved.temperature,
        api_key=resolved.api_key,
        base_url=resolved.base_url or None,
        timeout=resolved.timeout_seconds,
        max_retries=resolved.max_retries,
    )
