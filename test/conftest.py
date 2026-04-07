"""Shared pytest fixtures for async circuit breaker tests."""

from datetime import timedelta

import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from pytest import fixture

from asyncbreaker.state import CircuitBreakerState
from asyncbreaker.storage.memory import CircuitMemoryStorage
from asyncbreaker.storage.redis import CircuitRedisStorage

__all__ = ('async_storage', 'delta')


@pytest_asyncio.fixture(params=['memory', 'redis'])
async def async_storage(request):
    """Yield an async storage backend for each test run.

    The fixture is parametrized with ``memory`` (in-process) and ``redis`` (``fakeredis``).

    Yields:
        A :class:`~asyncbreaker.storage.base.CircuitBreakerStorage` instance.
    """
    if request.param == 'memory':
        yield CircuitMemoryStorage(CircuitBreakerState.CLOSED)
        return
    redis = FakeRedis(decode_responses=True)
    st = CircuitRedisStorage(redis)
    await st.initialize()
    try:
        yield st
    finally:
        await redis.aclose()


@fixture()
def delta():
    """Short :class:`datetime.timedelta` for reset timeouts in tests."""
    return timedelta(seconds=1)
