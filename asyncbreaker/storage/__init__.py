"""Pluggable async storage backends for :class:`~asyncbreaker.circuitbreaker.CircuitBreaker`."""

from .base import CircuitBreakerStorage, StorageError
from .redis import CircuitRedisStorage
from .memory import CircuitMemoryStorage

__all__ = (
    'CircuitBreakerStorage',
    'CircuitRedisStorage',
    'CircuitMemoryStorage',
    'StorageError',
)
