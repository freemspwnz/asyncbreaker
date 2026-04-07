"""Redis-backed async storage using ``redis.asyncio``."""

import logging
from datetime import datetime
from typing import Optional, Union

from ..state import CircuitBreakerState
from ..timeutil import naive_utc_to_posix_seconds, posix_seconds_to_naive_utc

from .base import CircuitBreakerStorage, StorageError

try:
    from redis.asyncio import Redis
    from redis.exceptions import RedisError
except ImportError:  # pragma: no cover
    Redis = None  # type: ignore[misc, assignment]
    RedisError = Exception  # type: ignore[misc, assignment]
    HAS_ASYNC_REDIS = False
else:
    HAS_ASYNC_REDIS = True


def _decode_str(value: Optional[Union[str, bytes]]) -> Optional[str]:
    """Decode Redis string values as UTF-8 text.

    Args:
        value: Raw value from Redis or ``None``.

    Returns:
        A ``str`` or ``None`` if ``value`` is ``None``.
    """
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode('utf-8')
    return str(value)


def _decode_int(value: Optional[Union[str, bytes]]) -> Optional[int]:
    """Parse an integer stored as string or bytes in Redis.

    Args:
        value: Raw value from Redis or ``None``.

    Returns:
        Parsed ``int`` or ``None`` if ``value`` is ``None``.
    """
    if value is None:
        return None
    if isinstance(value, bytes):
        return int(value.decode('utf-8'))
    return int(value)


def _decode_epoch_seconds(value: Optional[Union[str, bytes]]) -> Optional[float]:
    """Parse a Unix epoch stored as string (int or float) from Redis.

    Args:
        value: Raw value from Redis or ``None``.

    Returns:
        Seconds since epoch as ``float``, or ``None`` if ``value`` is ``None``.
    """
    if value is None:
        return None
    if isinstance(value, bytes):
        return float(value.decode('utf-8'))
    return float(str(value))


class CircuitRedisStorage(CircuitBreakerStorage):
    """Persisted circuit state via ``redis.asyncio`` (pipeline for atomic multi-key updates)."""

    BASE_NAMESPACE = 'asyncbreaker'

    logger = logging.getLogger(__name__)

    def __init__(
        self,
        redis_client: Redis,
        *,
        namespace: Optional[str] = None,
        init_state: CircuitBreakerState = CircuitBreakerState.CLOSED,
    ) -> None:
        """Attach to an async Redis client.

        Args:
            redis_client: Connected :class:`redis.asyncio.Redis` instance.
            namespace: Optional key prefix segment before ``asyncbreaker`` keys.
            init_state: Used when Redis is unavailable or keys are missing.

        Raises:
            ImportError: If the ``redis`` package with asyncio support is not installed.
        """
        if not HAS_ASYNC_REDIS:
            raise ImportError(
                'CircuitRedisStorage requires the redis package with asyncio support'
            )

        super().__init__('redis-async')
        self._redis = redis_client
        self._namespace_name = namespace
        self._init_state = init_state

    @property
    def constructor_state_hint(self) -> CircuitBreakerState:
        """Initial enum value matching the current Redis state."""
        return self._init_state

    def _key(self, key: str) -> str:
        """Build a namespaced Redis key.

        Args:
            key: Short suffix (``state``, ``fail_counter``, ``opened_at``).

        Returns:
            Full Redis key string.
        """
        parts = [self.BASE_NAMESPACE, key]
        if self._namespace_name:
            parts.insert(0, self._namespace_name)
        return ':'.join(parts)

    async def initialize(self) -> None:
        """Ensure default keys exist (``SETNX``). Safe to call after connect.

        Raises:
            StorageError: On Redis errors.
        """
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.setnx(self._key('state'), self._init_state.name)
                pipe.setnx(self._key('fail_counter'), 0)
                await pipe.execute()
        except RedisError as e:
            self.logger.error('RedisError during initialize', exc_info=True)
            raise StorageError(f'RedisError during initialize: {e}') from e

    async def get_state(self) -> CircuitBreakerState:
        """Return the current circuit state from Redis.

        If the ``state`` key is missing, :meth:`initialize` is used to create defaults.

        Returns:
            Parsed :class:`~asyncbreaker.state.CircuitBreakerState`, or ``_init_state`` if the
            stored value is missing or not a valid member name.

        Raises:
            StorageError: On Redis connection/command errors.
        """
        try:
            raw = await self._redis.get(self._key('state'))
        except RedisError as e:
            self.logger.error('RedisError on get_state', exc_info=True)
            raise StorageError(f'RedisError on get_state: {e}') from e

        name = _decode_str(raw) if raw is not None else None
        if name is None:
            await self.initialize()
            return self._init_state

        try:
            return getattr(CircuitBreakerState, name)
        except AttributeError:
            self.logger.warning('Unknown state %r in Redis, using initial state', name)
            return self._init_state

    async def increment_counter(self) -> None:
        """Atomically increment the failure counter.

        Raises:
            StorageError: On Redis errors.
        """
        try:
            await self._redis.incr(self._key('fail_counter'))
        except RedisError as e:
            self.logger.error('RedisError in increment_counter', exc_info=True)
            raise StorageError(f'RedisError during increment_counter: {e}') from e

    async def reset_counter(self) -> None:
        """Reset failure counter to zero.

        Raises:
            StorageError: On Redis errors.
        """
        try:
            await self._redis.set(self._key('fail_counter'), 0)
        except RedisError as e:
            self.logger.error('RedisError in reset_counter', exc_info=True)
            raise StorageError(f'RedisError during reset_counter: {e}') from e

    async def get_counter(self) -> int:
        """Return the failure counter from Redis, or ``0`` if the key is missing."""

        try:
            raw = await self._redis.get(self._key('fail_counter'))
            if raw is None:
                return 0
            return _decode_int(raw) or 0
        except RedisError as e:
            self.logger.error('RedisError in get_counter', exc_info=True)
            raise StorageError(f'RedisError during get_counter: {e}') from e

    async def get_opened_at(self) -> Optional[datetime]:
        """Return naive UTC datetime of last open, or ``None``."""
        try:
            raw = await self._redis.get(self._key('opened_at'))
            if raw is None:
                return None
            ts = _decode_epoch_seconds(raw)
            if ts is None:
                return None
            return posix_seconds_to_naive_utc(ts)
        except RedisError as e:
            self.logger.error('RedisError in get_opened_at', exc_info=True)
            raise StorageError(f'RedisError during get_opened_at: {e}') from e

    async def open_circuit(self, opened_at: datetime) -> None:
        """Atomically set OPEN and ``opened_at`` using a transactional pipeline.

        Args:
            opened_at: Naive UTC instant; treated as UTC when converting to epoch.

        Raises:
            StorageError: On Redis errors.
        """
        epoch = naive_utc_to_posix_seconds(opened_at)
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.set(self._key('state'), CircuitBreakerState.OPEN.name)
                pipe.set(self._key('opened_at'), str(epoch))
                await pipe.execute()
        except RedisError as e:
            self.logger.error('RedisError in open_circuit', exc_info=True)
            raise StorageError(f'RedisError during open_circuit: {e}') from e

    async def half_open_circuit(self) -> None:
        """Atomically set HALF_OPEN and delete ``opened_at``.

        Raises:
            StorageError: On Redis errors.
        """
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.set(self._key('state'), CircuitBreakerState.HALF_OPEN.name)
                pipe.delete(self._key('opened_at'))
                await pipe.execute()
        except RedisError as e:
            self.logger.error('RedisError in half_open_circuit', exc_info=True)
            raise StorageError(f'RedisError during half_open_circuit: {e}') from e

    async def close_circuit(self) -> None:
        """Atomically set CLOSED, reset counter, and delete ``opened_at``.

        Raises:
            StorageError: On Redis errors.
        """
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.set(self._key('state'), CircuitBreakerState.CLOSED.name)
                pipe.set(self._key('fail_counter'), 0)
                pipe.delete(self._key('opened_at'))
                await pipe.execute()
        except RedisError as e:
            self.logger.error('RedisError in close_circuit', exc_info=True)
            raise StorageError(f'RedisError during close_circuit: {e}') from e
