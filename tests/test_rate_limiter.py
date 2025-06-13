"""
Tests for rate limiting functionality
"""

import asyncio
import time

import pytest

from src.utils.rate_limiter import RateLimiter, RetryConfig, calculate_backoff, retry_async


@pytest.mark.asyncio
async def test_rate_limiter_basic():
    """Test basic rate limiting"""
    # 2 requests per second
    limiter = RateLimiter(rate=2.0, burst=2)

    start = time.monotonic()

    # First two should be immediate (burst)
    await limiter.acquire()
    await limiter.acquire()

    # Third should wait
    await limiter.acquire()

    elapsed = time.monotonic() - start

    # Should take at least 0.5 seconds (1/2 rate)
    assert elapsed >= 0.4  # Allow small margin


@pytest.mark.asyncio
async def test_rate_limiter_concurrent():
    """Test rate limiting with concurrent requests"""
    limiter = RateLimiter(rate=1.0, burst=1)

    async def make_request(id):
        await limiter.acquire()
        return time.monotonic(), id

    start = time.monotonic()

    # Make 3 concurrent requests
    results = await asyncio.gather(make_request(1), make_request(2), make_request(3))

    times = [r[0] - start for r in results]

    # First should be immediate
    assert times[0] < 0.1

    # Others should be spaced by ~1 second
    assert 0.8 <= times[1] <= 1.2
    assert 1.8 <= times[2] <= 2.2


def test_calculate_backoff():
    """Test exponential backoff calculation"""
    config = RetryConfig(initial_delay=1.0, exponential_base=2.0, max_delay=10.0, jitter=False)

    # First retry
    delay = calculate_backoff(1, config)
    assert delay == 1.0

    # Second retry
    delay = calculate_backoff(2, config)
    assert delay == 2.0

    # Third retry
    delay = calculate_backoff(3, config)
    assert delay == 4.0

    # Should cap at max_delay
    delay = calculate_backoff(10, config)
    assert delay == 10.0


def test_calculate_backoff_with_jitter():
    """Test backoff with jitter"""
    config = RetryConfig(initial_delay=1.0, exponential_base=2.0, jitter=True)

    # With jitter, delay should be between 0.5x and 1.5x base delay
    delays = [calculate_backoff(2, config) for _ in range(10)]

    # All should be in range [1.0, 3.0] (2.0 * 0.5 to 2.0 * 1.5)
    assert all(1.0 <= d <= 3.0 for d in delays)

    # Should have some variation
    assert len(set(delays)) > 1


@pytest.mark.asyncio
async def test_retry_async_success():
    """Test retry with successful function"""
    call_count = 0

    async def func():
        nonlocal call_count
        call_count += 1
        return "success"

    result = await retry_async(func)

    assert result == "success"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_async_eventual_success():
    """Test retry with eventual success"""
    call_count = 0

    async def func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("Not yet")
        return "success"

    config = RetryConfig(max_attempts=3, initial_delay=0.01)
    result = await retry_async(func, config=config, retry_on=(ValueError,))

    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_async_all_fail():
    """Test retry when all attempts fail"""
    call_count = 0

    async def func():
        nonlocal call_count
        call_count += 1
        raise ValueError(f"Attempt {call_count}")

    config = RetryConfig(max_attempts=3, initial_delay=0.01)

    with pytest.raises(ValueError) as exc_info:
        await retry_async(func, config=config, retry_on=(ValueError,))

    assert "Attempt 3" in str(exc_info.value)
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_async_specific_exceptions():
    """Test retry only on specific exceptions"""
    call_count = 0

    async def func():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("Retry this")
        else:
            raise TypeError("Don't retry this")

    config = RetryConfig(max_attempts=3, initial_delay=0.01)

    # Should not retry TypeError
    with pytest.raises(TypeError):
        await retry_async(func, config=config, retry_on=(ValueError,))

    assert call_count == 2  # First attempt + one retry
