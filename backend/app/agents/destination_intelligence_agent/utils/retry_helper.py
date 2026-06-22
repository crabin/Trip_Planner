"""Small retry utilities shared by destination-intelligence integrations."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
import time
from typing import Any, ParamSpec, TypeVar, cast


P = ParamSpec("P")
R = TypeVar("R")
_UNSET = object()


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for bounded exponential-backoff retries."""

    max_attempts: int = 3
    initial_delay: float = 1.0
    max_delay: float = 4.0
    backoff_multiplier: float = 2.0
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.initial_delay < 0 or self.max_delay < 0:
            raise ValueError("retry delays cannot be negative")
        if self.backoff_multiplier < 1:
            raise ValueError("backoff_multiplier must be at least 1")


SEARCH_API_RETRY_CONFIG = RetryConfig()


def with_graceful_retry(
    config: RetryConfig,
    *,
    default_return: Any = _UNSET,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Retry a call and optionally return a fallback after the final failure."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            delay = config.initial_delay
            for attempt in range(1, config.max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except config.retryable_exceptions:
                    if attempt == config.max_attempts:
                        if default_return is _UNSET:
                            raise
                        return cast(R, default_return)
                    if delay:
                        time.sleep(delay)
                    delay = min(delay * config.backoff_multiplier, config.max_delay)

            raise RuntimeError("retry loop exited unexpectedly")

        return wrapper

    return decorator
