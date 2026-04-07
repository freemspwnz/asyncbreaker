Usage
=====

Calling functions through the breaker
--------------------------------------

Use :meth:`asyncbreaker.circuitbreaker.CircuitBreaker.call` (async) or the decorator.
The decorator only accepts **async** functions.

.. code:: python

    from asyncbreaker import CircuitBreaker

    breaker = CircuitBreaker()

    @breaker
    async def work():
        ...

    result = await breaker.call(work)

If you pass a decorated function into :meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.call`,
the breaker avoids applying logic twice (``ignore_on_call`` on the wrapper). To change that,
pass ``ignore_on_call=False`` to the decorator: ``@breaker(ignore_on_call=False)``.

Manual open, half-open, close
------------------------------

All of these are **async** and update storage plus notify listeners:

* :meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.open` — trip the breaker (state OPEN, ``opened_at`` set atomically in Redis storage).
* :meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.half_open` — allow one trial call and **clear** ``opened_at`` in storage (memory and Redis) so :meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.compute_opens_at` / :meth:`~.circuitbreaker.CircuitBreaker.get_time_until_open` do not reflect a stale OPEN window while HALF_OPEN.
* :meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.close` — force CLOSED and reset the failure counter.

.. code:: python

    await breaker.open()
    # ...
    await breaker.close()

State and metrics (async)
-------------------------

Storage is always accessed with ``await``:

* :meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.get_fail_counter`
* :meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.get_current_state`
* :meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.fetch_state` — refresh cached behavioral state from storage (e.g. another process changed Redis).
* :meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.compute_opens_at` — naive UTC instant when the OPEN reset window ends, or ``None`` if there is no active window (CLOSED, or HALF_OPEN with ``opened_at`` cleared).
* :meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.set_circuit_state` — persist an enum value and swap the cached state object. Pass a :class:`~asyncbreaker.state.CircuitBreakerState` member; other values raise ``ValueError``.

Note: :meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.get_current_state` reads storage only; the in-memory behavioral state is refreshed on :meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.fetch_state` and before each :meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.call`.

Async listeners
---------------

Subclass :class:`asyncbreaker.listener.CircuitBreakerListener` and override **async** methods:

* ``before_call``, ``success``, ``failure``, ``state_change`` — all are ``async def``.

.. code:: python

    import logging

    from asyncbreaker import CircuitBreaker, CircuitBreakerListener

    logger = logging.getLogger(__name__)

    class LogListener(CircuitBreakerListener):
        async def state_change(self, breaker, old, new):
            logger.info("%s -> %s", old.state, new.state)

    breaker = CircuitBreaker(listeners=[LogListener()])

Register or remove listeners with :meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.add_listener`
and :meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.remove_listener`.

Redis storage
-------------

Use a ``redis.asyncio.Redis`` client and :class:`asyncbreaker.storage.redis.CircuitRedisStorage`.
Call ``await storage.initialize()`` once after the client is ready (``SETNX`` defaults).

.. code:: python

    import redis.asyncio as redis

    from asyncbreaker import CircuitBreaker
    from asyncbreaker.storage.redis import CircuitRedisStorage

    client = redis.from_url("redis://localhost:6379/0", decode_responses=True)
    storage = CircuitRedisStorage(client, namespace="myapp")
    await storage.initialize()

    breaker = CircuitBreaker(state_storage=storage)

Ignoring specific exceptions
-----------------------------

Pass types or callables to ``exclude`` when constructing the breaker, or use
:meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.add_excluded_exception` /
:meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.remove_excluded_exception`.

.. code:: python

    import sqlite3

    breaker = CircuitBreaker(exclude=[sqlite3.OperationalError])

Callable filters are supported:

.. code:: python

    breaker = CircuitBreaker(
        exclude=[lambda e: type(e).__name__ == "HTTPError" and getattr(e, "status", 500) < 500]
    )
