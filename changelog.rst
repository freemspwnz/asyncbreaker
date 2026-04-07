Changelog
=========

2.0.0 (April 2026)
------------------

Maintainer: Sergey Turbinov.

**asyncbreaker** is a maintained fork and major refactor of the asyncio circuit-breaker line
(**pybreaker** → **aiobreaker** → **asyncbreaker**). This release establishes the production API:
asyncio-first, pluggable async storage, and explicit time semantics. Python **3.10+** is
required.

Summary
~~~~~~~

* Single **async** surface: guarded calls, listener hooks, and persistence all use
  ``async``/``await``.
* **State** (CLOSED / OPEN / HALF_OPEN) and failure counts live in a pluggable
  :class:`~asyncbreaker.storage.base.CircuitBreakerStorage`, so multiple workers can share Redis-backed
  state; the breaker **refreshes** its cached behavioral state from storage before each
  :meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.call`.
* **Wall-clock** behavior for OPEN windows is centralized in :mod:`asyncbreaker.timeutil` (naive UTC),
  keeping Redis timestamps, monitoring helpers, and the state machine aligned.

Breaking changes
~~~~~~~~~~~~~~~~

* **Package and imports:** install and import **asyncbreaker** (not ``aiobreaker`` / ``pybreaker``).
  Public symbols are exported from :mod:`asyncbreaker` (including storage types and
  :exc:`~asyncbreaker.storage.base.StorageError`).
* **Async-only API:** there is no synchronous ``call``. Use
  ``await breaker.call(...)``. Manual transitions are
  ``await breaker.open()`` / ``await breaker.close()`` / ``await breaker.half_open()`` (or
  ``await breaker.set_circuit_state(...)``).
* **Listeners are async:** subclass :class:`~asyncbreaker.listener.CircuitBreakerListener` and
  implement ``async def`` hooks (``before_call``, ``failure``, ``success``, ``state_change``).
* **Storage is async:** backends implement :class:`~asyncbreaker.storage.base.CircuitBreakerStorage`
  (async getters/setters). Synchronous storage adapters are not supported.
* **Decorator:** only **async** functions are accepted; ordinary ``def`` callables are
  rejected. The decorator can mark wrappers so nested ``call(wrapper)`` does not double-apply
  the breaker (``ignore_on_call`` / ``_ignore_on_call``).
* **Removed:** synchronous generator wrapping, threading-oriented paths, and Tornado-specific
  integration from older forks.

Features and behavior
~~~~~~~~~~~~~~~~~~~~~

* **Default reset window:** if ``timeout_duration`` is omitted, it defaults to **60 seconds**
  (still overridable via constructor or property).
* **Excluded errors:** ``exclude`` accepts exception types and callables
  ``(exc) -> truthy`` to treat an error as non-system (counter behaves like success).
* **CircuitBreakerError:** carries ``reopen_time`` (naive UTC when applicable);
  :attr:`~asyncbreaker.state.CircuitBreakerError.time_remaining` and
  :meth:`~asyncbreaker.state.CircuitBreakerError.sleep_until_open` for callers and metrics.
* **Monitoring helpers** on the breaker: :meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.compute_opens_at`,
  :meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.get_time_until_open`,
  :meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.sleep_until_open`, plus async accessors for
  counter and ``opened_at``.
* **Explicit state objects:** :class:`~asyncbreaker.state.CircuitBreakerState` maps enum members to
  small behavior classes (CLOSED / OPEN / HALF_OPEN). OPEN → HALF_OPEN transition after the
  timeout is integrated into the OPEN state’s call path before the guarded function runs, so
  listener order matches the state that actually executes the attempt.

Storage and Redis
~~~~~~~~~~~~~~~~~

* **In-memory:** :class:`~asyncbreaker.storage.memory.CircuitMemoryStorage` for tests and single-process
  use.
* **Redis:** :class:`~asyncbreaker.storage.redis.CircuitRedisStorage` uses **redis.asyncio**; optional
  dependency via ``pip install asyncbreaker[redis]``.
* **Construction without await:** storage exposes :attr:`~asyncbreaker.storage.base.CircuitBreakerStorage.constructor_state_hint`
  so :class:`~asyncbreaker.circuitbreaker.CircuitBreaker` can build an initial behavioral state
  synchronously.
* **Atomic writes:** OPEN / HALF_OPEN / CLOSED transitions in Redis use transactional **pipelines**
  (e.g. state + ``opened_at`` + counter) to keep keys consistent under concurrency.
* **``opened_at`` semantics:** moving to HALF_OPEN clears ``opened_at`` in both backends so
  time-based helpers do not report a stale OPEN window.
* **Epoch precision:** ``opened_at`` round-trips via fractional epoch seconds where applicable,
  consistent with :meth:`datetime.datetime.timestamp`.

Migration notes
~~~~~~~~~~~~~~~

* Replace ``from aiobreaker ...`` / ``pybreaker`` imports with ``from asyncbreaker ...``.
* Add ``await`` to every ``call``, listener method, and storage operation you implement or
  override.
* Pass a :class:`~asyncbreaker.storage.redis.CircuitRedisStorage` only with an async Redis client from
  ``redis.asyncio``; call :meth:`~asyncbreaker.storage.redis.CircuitRedisStorage.initialize` where
  documented for default keys.


Earlier fork history (pybreaker / aiobreaker)
----------------------------------------------

FORK 1.1.0 (Jan 14, 2019)

* Add logic to stop calling decorator trigger twice
* Fix bug with timeout window growing with additional breakers defined (Thanks @shawndrape)
* Remove threading support (unneeded with asyncio)

FORK 1.0.0 (Aug 12, 2018)

* Move over to asyncio
* Drop < 3.4 support
* Drop tornado support
* Async call support

Version 0.4.4 (May 21, 2018)

* Fix PyPI release

Version 0.4.3 (May 21, 2018)

* Re-initialize state on Redis if missing (Thanks @scascketta!)
* Add trigger exception into the CircuitBreakerError (Thanks @tczhaodachuan!)

Version 0.4.2 (November 9, 2017)

* Add optional name to CircuitBreaker (Thanks @chrisvaughn!)

Version 0.4.1 (October 2, 2017)

* Get initial CircuitBreaker state from state_storage (Thanks @alukach!)

Version 0.4.0 (June 23, 2017)

* Added optional support for asynchronous Tornado calls (Thanks @jeffrand!)
* Fixed typo (issue #19) (Thanks @jeffrand!)


Version 0.3.3 (June 2, 2017)

* Fixed bug that caused pybreaker to break (!) if redis package was not
  present (Thanks @phillbaker!)


Version 0.3.2 (June 1, 2017)

* Added support for optional Redis backing (Thanks @phillbaker!)
* Fixed: Should listener.failure be called when the circuit is closed
  and a call fails? (Thanks @sj175 for the report!)
* Fixed: Wrapped function is called twice during successful call in open
  state (Thanks @jstordeur!)


Version 0.3.1 (January 25, 2017)

* Added support for optional Redis backing


Version 0.3.0 (September 1, 2016)

* Fixed generator issue. (Thanks @dpdornseifer!)


Version 0.2.3 (July 25, 2014)

* Added support to generator functions. (Thanks @mauriciosl!)


Version 0.2.1 (October 23, 2010)

* Fixed a few concurrency bugs.


Version 0.2 (October 20, 2010)

* Several API changes, breaks backwards compatibility.
* New CircuitBreakerListener class that allows the user to listen to events in
  a circuit breaker without the need to subclass CircuitBreaker.
* Decorator now uses 'functools.wraps' to avoid loss of information on decorated
  functions.


Version 0.1.1 (October 17, 2010)

* Instance of CircuitBreaker can now be used as a decorator.
* Python 2.6+ is now required in order to make the same code base compatible
  with Python 3+.


Version 0.1 (October 16, 2010)

* First public release.
