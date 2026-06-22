"""LangChain-based OpenAI-compatible client for destination intelligence."""

from collections.abc import Generator
from datetime import datetime
from pathlib import Path
import sys
from typing import Any, Optional

if not __package__:
    backend_dir = Path(__file__).resolve().parents[4]
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

from app import config

class LLMClient:
    """Small compatibility wrapper around ``langchain_openai.ChatOpenAI``."""

    def __init__(
        self,
        api_key: str,
        model_name: str,
        base_url: Optional[str] = None,
    ) -> None:
        if not api_key:
            raise ValueError("Destination Intelligence Agent LLM API key is required.")
        if not model_name:
            raise ValueError("Destination Intelligence Agent model name is required.")

        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url
        self.provider = model_name
        self.timeout = float(config.LLM_TIMEOUT_SECONDS)
        self.client = self.build_chat_llm()

    def build_chat_llm(self) -> Any:
        """Create the project's LangChain OpenAI-compatible chat model."""
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "langchain_openai is required by Destination Intelligence Agent."
            ) from exc

        return ChatOpenAI(
            model=self.model_name,
            api_key=self.api_key,
            base_url=self.base_url or None,
            timeout=self.timeout,
            max_retries=config.LLM_MAX_RETRIES,
        )

    def invoke(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        """Invoke the model and return its normalized text response."""
        messages = self._build_messages(system_prompt, user_prompt)
        allowed_keys = {
            "temperature",
            "top_p",
            "presence_penalty",
            "frequency_penalty",
        }
        model_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key in allowed_keys and value is not None
        }
        timeout = kwargs.get("timeout", self.timeout)

        response = self.client.invoke(messages, timeout=timeout, **model_kwargs)
        return self.validate_response(response.content)

    def stream_invoke(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs: Any,
    ) -> Generator[str, None, None]:
        """Invoke the model in streaming mode and yield text chunks."""
        messages = self._build_messages(system_prompt, user_prompt)
        allowed_keys = {
            "temperature",
            "top_p",
            "presence_penalty",
            "frequency_penalty",
        }
        model_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key in allowed_keys and value is not None
        }
        timeout = kwargs.get("timeout", self.timeout)

        for chunk in self.client.stream(messages, timeout=timeout, **model_kwargs):
            if isinstance(chunk.content, str) and chunk.content:
                yield chunk.content

    def stream_invoke_to_string(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs: Any,
    ) -> str:
        """Consume a streaming response and return one complete string."""
        return "".join(self.stream_invoke(system_prompt, user_prompt, **kwargs))

    @staticmethod
    def validate_response(response: Optional[str]) -> str:
        """Normalize an empty or whitespace-padded model response."""
        if response is None:
            return ""
        return response.strip()

    def get_model_info(self) -> dict[str, Any]:
        """Return non-secret model metadata for logs and diagnostics."""
        return {
            "provider": self.provider,
            "model": self.model_name,
            "api_base": self.base_url or "default",
        }

    @staticmethod
    def _build_messages(system_prompt: str, user_prompt: str) -> list[tuple[str, str]]:
        current_time = datetime.now().strftime("%Y年%m月%d日%H时%M分")
        time_prefix = f"今天的实际时间是{current_time}"
        human_prompt = f"{time_prefix}\n{user_prompt}" if user_prompt else time_prefix
        return [("system", system_prompt), ("human", human_prompt)]


