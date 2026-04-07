asyncbreaker
==========

**asyncbreaker** is an **asyncio-first** Python implementation of the Circuit Breaker pattern
from Michael T. Nygard's book `Release It!`_.

Circuit breakers let one subsystem fail without taking down the whole application: you wrap
risky calls (often I/O or integration boundaries) so that repeated failures **trip** the breaker,
subsequent calls fail fast for a **reset timeout**, then a single **trial** call may close
the circuit again.

Lineage
-------

* **pybreaker** (Daniel Fernandes Martins) — original design.
* **aiobreaker fork** (Alexander Lyon) — asyncio instead of Tornado, packaging experiments.
* **Current line** — maintained by Sergey Turbinov; substantial rewrite toward a pure async API,
  async storage, and async listeners. Contact: `@freems`_ on Telegram.

.. _`Release It!`: https://pragprog.com/titles/mnee2/release-it-second-edition/
.. _pybreaker: https://github.com/danielfm/pybreaker
.. _@freems: https://t.me/freems

Features
--------

* Async ``CircuitBreaker`` — use ``await breaker.call(...)``
* Configurable failure threshold (``fail_max``) and reset window (``timeout_duration``)
* Excluded exceptions and predicate callables (business vs system errors)
* Multiple **async** ``CircuitBreakerListener`` instances
* Pluggable **async** storage: in-process memory or Redis via ``redis.asyncio``
* Optional ``redis`` extra for Redis-backed storage

Requirements
------------

Python **3.10+** (async patterns and typing used throughout).

Installation
------------

.. code:: bash

    pip install asyncbreaker

With Redis support (``redis`` package):

.. code:: bash

    pip install asyncbreaker[redis]

Usage
-----

Create a breaker per integration point. Only **async** callables are supported; the decorator
rejects ordinary ``def`` functions.

.. code:: python

    from datetime import timedelta

    from asyncbreaker import CircuitBreaker

    api_breaker = CircuitBreaker(fail_max=5, timeout_duration=timedelta(seconds=60))

    @api_breaker
    async def fetch_remote():
        ...

    # or explicitly:
    await api_breaker.call(fetch_remote)

See the **Usage** chapter in the full documentation (``docs/``) for listeners, storage,
manual ``open`` / ``close`` / ``half_open``, and exclusion rules.

Documentation
-------------

Build locally:

.. code:: bash

    pip install -e '.[docs]'
    sphinx-build docs/source docs/build

The HTML entry point is ``docs/build/index.html``.

License
-------

BSD 3-Clause; see ``license.md``. This project bundles copyright from the pybreaker lineage;
additional copyright applies to the asyncio rewrite (see ``license.md``).
