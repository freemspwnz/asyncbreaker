"""Async listener protocol for circuit breaker lifecycle hooks.

Subclasses override the async methods they care about; default implementations are no-ops.
"""

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from asyncbreaker.circuitbreaker import CircuitBreaker
    from asyncbreaker.state import CircuitBreakerBaseState


class CircuitBreakerListener:
    """Async hooks for guarded calls and state transitions."""

    async def before_call(
        self,
        breaker: 'CircuitBreaker',
        func: Callable,
        *args,
        **kwargs,
    ) -> None:
        """Called immediately before ``func`` is awaited (after the state's own ``before_call``).

        If the state machine performs an automatic transition before ``func`` (for example
        OPEN → HALF_OPEN once the reset window has elapsed), that transition finishes first;
        this hook then runs in the state that will actually execute ``func``.

        Args:
            breaker: The :class:`~asyncbreaker.circuitbreaker.CircuitBreaker` instance.
            func: Async function about to be invoked.
            `*args`: Positional arguments passed to ``func``.
            `**kwargs`: Keyword arguments passed to ``func``.
        """

    async def failure(
        self,
        breaker: 'CircuitBreaker',
        exception: Exception,
    ) -> None:
        """Called when the guarded call raises a *system* error (counts toward the threshold).

        Args:
            breaker: The breaker instance.
            exception: The exception raised by the guarded function.
        """

    async def success(self, breaker: 'CircuitBreaker') -> None:
        """Called when the guarded call completes without exception."""

    async def state_change(
        self,
        breaker: 'CircuitBreaker',
        old: 'CircuitBreakerBaseState',
        new: 'CircuitBreakerBaseState',
    ) -> None:
        """Called when the cached behavioral state object changes (after storage sync).

        Args:
            breaker: The breaker instance.
            old: Previous state behavior object.
            new: New state behavior object.
        """
