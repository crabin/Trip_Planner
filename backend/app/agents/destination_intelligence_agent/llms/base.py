"""LangChain-based OpenAI-compatible client for destination intelligence."""

from collections.abc import Generator
from datetime import datetime
from pathlib import Path
import sys
import time
from typing import Any, Optional

if not __package__:
    backend_dir = Path(__file__).resolve().parents[4]
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

try:
    from loguru import logger
except ImportError:
    import logging

    class _FallbackLogger:
        def __init__(self) -> None:
            self._logger = logging.getLogger(__name__)

        def warning(self, message: str, *args: Any) -> None:
            self._logger.warning(message.format(*args) if args else message)

    logger = _FallbackLogger()

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
        self.max_retries = max(0, int(config.LLM_MAX_RETRIES))
        self.retry_delay = 1.0
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
            max_retries=self.max_retries,
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
        for retry_index in range(self.max_retries + 1):
            try:
                return "".join(
                    self.stream_invoke(system_prompt, user_prompt, **kwargs)
                )
            except Exception as exc:
                retries_exhausted = retry_index >= self.max_retries
                if retries_exhausted or not self._is_retryable_stream_error(exc):
                    raise

                retry_number = retry_index + 1
                delay = min(self.retry_delay * (2**retry_index), 4.0)
                logger.warning(
                    "LLM流式响应暂时失败（{}），将在{:.1f}秒后重试 {}/{}",
                    type(exc).__name__,
                    delay,
                    retry_number,
                    self.max_retries,
                )
                if delay:
                    time.sleep(delay)

        raise RuntimeError("LLM流式响应重试循环异常退出")

    @staticmethod
    def _is_retryable_stream_error(error: Exception) -> bool:
        """Return whether an OpenAI-compatible streaming failure is transient."""
        try:
            from openai import (
                APIConnectionError,
                APIError,
                APIStatusError,
                APITimeoutError,
                RateLimitError,
            )
        except ImportError:
            return False

        if isinstance(error, APIStatusError):
            status_code = error.status_code
            return status_code in {408, 409, 429} or status_code >= 500

        return isinstance(
            error,
            (APIConnectionError, APITimeoutError, RateLimitError, APIError),
        )

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
