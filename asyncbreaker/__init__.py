# -*- coding:utf-8 -*-

"""Asyncio-first Circuit Breaker pattern (see *Release It!* by Michael T. Nygard).

Public API:

* :class:`~asyncbreaker.circuitbreaker.CircuitBreaker` — use ``await`` for guarded calls,
  storage-backed state, and async listeners.
* :class:`~asyncbreaker.storage.base.CircuitBreakerStorage` — in-memory or Redis backends.

Further reading: https://pragprog.com/titles/mnee2/release-it-second-edition/
"""

from .circuitbreaker import CircuitBreaker
from .listener import CircuitBreakerListener
from .state import (
    CircuitBreakerError,
    CircuitBreakerState,
)
from .storage import (
    CircuitMemoryStorage,
    CircuitRedisStorage,
    CircuitBreakerStorage,
    StorageError,
)

__all__ = (
    'CircuitBreaker',
    'CircuitBreakerListener',
    'CircuitBreakerError',
    'CircuitBreakerState',
    'CircuitMemoryStorage',
    'CircuitRedisStorage',
    'CircuitBreakerStorage',
    'StorageError',
)
