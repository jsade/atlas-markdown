"""
Rate limiting and retry logic for web scraping
"""

import asyncio
import logging
import random
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, Awaitable, Optional, Tuple, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RateLimiter:
    """Token bucket rate limiter"""

    def __init__(self, rate: float = 1.0, burst: int = 1):
        """
        Initialize rate limiter

        Args:
            rate: Requests per second
            burst: Maximum burst size
        """
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> None:
        """Acquire tokens, waiting if necessary"""
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.last_update = now

                # Add new tokens based on elapsed time
                self.tokens = min(self.burst, self.tokens + elapsed * self.rate)

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return

                # Calculate wait time
                wait_time = (tokens - self.tokens) / self.rate
                await asyncio.sleep(wait_time)


class RetryConfig:
    """Configuration for retry behavior"""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter


def calculate_backoff(attempt: int, config: RetryConfig) -> float:
    """Calculate exponential backoff delay"""
    delay = min(config.initial_delay * (config.exponential_base ** (attempt - 1)), config.max_delay)

    if config.jitter:
        # Add random jitter (0.5x to 1.5x)
        delay = delay * (0.5 + random.random())

    return delay


async def retry_async(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    config: Optional[RetryConfig] = None,
    retry_on: Tuple[Type[Exception], ...] = (Exception,),
    **kwargs: Any,
) -> T:
    """
    Retry an async function with exponential backoff

    Args:
        func: Async function to retry
        config: Retry configuration
        retry_on: Tuple of exceptions to retry on
        *args, **kwargs: Arguments for the function

    Returns:
        Function result

    Raises:
        Last exception if all retries fail
    """
    if config is None:
        config = RetryConfig()

    last_exception: Optional[Exception] = None

    for attempt in range(1, config.max_attempts + 1):
        try:
            return await func(*args, **kwargs)

        except retry_on as e:
            last_exception = e

            if attempt == config.max_attempts:
                logger.error(f"All {config.max_attempts} attempts failed for {func.__name__}")
                raise

            delay = calculate_backoff(attempt, config)
            logger.warning(
                f"Attempt {attempt} failed for {func.__name__}: {str(e)}. "
                f"Retrying in {delay:.1f}s..."
            )

            await asyncio.sleep(delay)

    # Should never reach here
    if last_exception:
        raise last_exception
    else:
        raise RuntimeError("Retry failed without exception")


def with_retry(
    config: Optional[RetryConfig] = None, retry_on: Tuple[Type[Exception], ...] = (Exception,)
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator for adding retry logic to async functions"""

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await retry_async(func, *args, config=config, retry_on=retry_on, **kwargs)

        return wrapper

    return decorator


class ThrottledScraper:
    """Base class for rate-limited scraping operations"""

    def __init__(
        self, rate_limiter: RateLimiter, retry_config: Optional[RetryConfig] = None
    ) -> None:
        self.rate_limiter = rate_limiter
        self.retry_config = retry_config or RetryConfig()

    async def throttled_request(
        self, func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any
    ) -> T:
        """Execute a function with rate limiting and retry"""
        # Acquire rate limit token
        await self.rate_limiter.acquire()

        # Execute with retry
        return await retry_async(func, *args, config=self.retry_config, **kwargs)
