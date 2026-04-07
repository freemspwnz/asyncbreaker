Storage backends
================

All backends implement :class:`asyncbreaker.storage.base.CircuitBreakerStorage` with **async**
methods (``await storage.get_state()``, etc.). Implementations must **clear** ``opened_at`` when
transitioning to HALF_OPEN so callers using time-based helpers on :class:`~asyncbreaker.circuitbreaker.CircuitBreaker`
do not see an outdated OPEN deadline while a trial is in progress.

.. automodule:: asyncbreaker.storage

Base class
----------

.. automodule:: asyncbreaker.storage.base

Memory storage
--------------

.. automodule:: asyncbreaker.storage.memory

Redis storage (``redis.asyncio``)
---------------------------------

:class:`asyncbreaker.storage.redis.CircuitRedisStorage` expects a connected
:class:`redis.asyncio.Redis` client. Use ``decode_responses=True`` if you want string values
from Redis; the implementation accepts both ``str`` and ``bytes`` for reads.

.. automodule:: asyncbreaker.storage.redis
