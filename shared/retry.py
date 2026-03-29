"""Exponential backoff retry decorator."""

import asyncio
import functools
import logging
import random

logger = logging.getLogger(__name__)


def retry(max_attempts: int = 3, base_delay: float = 1.0, exceptions: tuple = (Exception,)):
    """Decorator for async functions with exponential backoff + jitter.

    Args:
        max_attempts: Maximum number of attempts.
        base_delay: Base delay in seconds (doubles each attempt).
        exceptions: Tuple of exception types to catch.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        logger.error(f"{func.__name__} failed after {max_attempts} attempts: {e}")
                        raise
                    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
                    logger.warning(f"{func.__name__} attempt {attempt}/{max_attempts} failed: {e}. Retrying in {delay:.1f}s")
                    await asyncio.sleep(delay)
            raise last_exception

        return wrapper

    return decorator
