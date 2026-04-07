"""Circuit breaker states, errors, and the state enum.

Implements CLOSED (count failures), OPEN (fail fast until timeout), and HALF_OPEN (single trial).
Behavior objects persist counters and timestamps through :class:`~asyncbreaker.circuitbreaker.CircuitBreaker`
helpers (not by touching storage directly).
"""

from abc import ABC
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Optional, TypeVar, Awaitable, TYPE_CHECKING

from .timeutil import (
    naive_utc_remaining_until,
    reopen_deadline,
    sleep_for_remaining,
    naive_utc_now,
)

if TYPE_CHECKING:
    from asyncbreaker.circuitbreaker import CircuitBreaker


class CircuitBreakerError(Exception):
    """Raised when a call is rejected because the circuit is open or a trial fails.

    Attributes:
        message: Human-readable explanation.
        reopen_time: Naive UTC instant after which the OPEN window may end, if applicable.
    """

    def __init__(self, message: str, reopen_time: Optional[datetime] = None) -> None:
        super().__init__(message)
        self.message = message
        self.reopen_time = reopen_time

    @property
    def time_remaining(self) -> timedelta:
        """Time left until :attr:`reopen_time`, or zero if past / unknown."""
        return naive_utc_remaining_until(self.reopen_time)

    async def sleep_until_open(self) -> None:
        """Sleep until :attr:`reopen_time` if it is still in the future."""
        await sleep_for_remaining(self.time_remaining)


T = TypeVar('T')


class CircuitBreakerBaseState(ABC):
    """Shared template for executing guarded calls in a given circuit state."""

    def __init__(self, breaker: 'CircuitBreaker', state: 'CircuitBreakerState') -> None:
        """Attach this behavior object to a breaker and enum member.

        Args:
            breaker: Owning :class:`~asyncbreaker.circuitbreaker.CircuitBreaker`.
            state: Enum member identifying this behavior.
        """
        self._breaker = breaker
        self._state = state

    @property
    def state(self) -> 'CircuitBreakerState':
        """Enum member for this behavior (CLOSED, OPEN, or HALF_OPEN)."""
        return self._state

    async def _handle_error(self, _func: Callable, exception: Exception) -> None:
        """Increment counter and run failure hooks, or treat as success if excluded.

        Always re-raises ``exception`` after handling (or raises :class:`CircuitBreakerError`
        from :meth:`on_failure`).

        Args:
            _func: The guarded callable (for listener context).
            exception: Exception raised by the guarded call.
        """
        if self._breaker.is_system_error(exception):
            await self._breaker._increment_failure_counter()
            for listener in self._breaker.listeners:
                await listener.failure(self._breaker, exception)
            await self.on_failure(exception)
        else:
            await self._handle_success()
        raise exception

    async def _handle_success(self) -> None:
        """Reset counter, run :meth:`on_success`, and notify success listeners."""
        await self._breaker._reset_failure_counter()
        await self.on_success()
        for listener in self._breaker.listeners:
            await listener.success(self._breaker)

    async def call(self, func: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        """Invoke ``func`` with hooks; route success and failure through state logic.

        Args:
            func: Async callable to run.
            `*args`: Positional arguments for ``func``.
            `**kwargs`: Keyword arguments for ``func``.

        Returns:
            Result of awaiting ``func``.

        Raises:
            CircuitBreakerError: From :meth:`before_call` or :meth:`on_failure` in subclasses.
            Exception: Propagates the original exception after failure handling when applicable.
        """
        await self.before_call(func, *args, **kwargs)
        for listener in self._breaker.listeners:
            await listener.before_call(self._breaker, func, *args, **kwargs)

        try:
            ret = await func(*args, **kwargs)
        except Exception as e:
            await self._handle_error(func, e)
        else:
            await self._handle_success()
        return ret

    async def before_call(self, func: Callable, *args, **kwargs) -> None:
        """Hook run before listeners and the guarded call; may raise :class:`CircuitBreakerError`."""
        pass

    async def on_success(self) -> None:
        """Hook after a successful call, before success listeners (counter already reset)."""
        pass

    async def on_failure(self, exception: Exception) -> None:
        """Hook after a system failure (counter already incremented)."""
        pass


class CircuitClosedState(CircuitBreakerBaseState):
    """CLOSED: accumulate failures; open when the counter reaches ``fail_max``."""

    def __init__(self, breaker: 'CircuitBreaker') -> None:
        super().__init__(breaker, CircuitBreakerState.CLOSED)

    async def on_failure(self, exception: Exception) -> None:
        """Open the circuit if the failure threshold is reached.

        Raises:
            CircuitBreakerError: When the threshold is reached, chaining ``exception``.
        """
        counter = await self._breaker.get_fail_counter()
        if counter >= self._breaker.fail_max:
            await self._breaker.open()
            opened_at = await self._breaker.get_opened_at()
            reopen = reopen_deadline(opened_at, self._breaker.timeout_duration)
            raise CircuitBreakerError(
                'Failures threshold reached, circuit breaker opened.',
                reopen,
            ) from exception


class CircuitOpenState(CircuitBreakerBaseState):
    """OPEN: reject calls until ``opened_at + timeout``; then transition to half-open and retry."""

    def __init__(self, breaker: 'CircuitBreaker') -> None:
        super().__init__(breaker, CircuitBreakerState.OPEN)

    async def before_call(self, func, *args, **kwargs) -> None:
        """Fail fast while the reset window has not elapsed.

        Raises:
            CircuitBreakerError: While the circuit must stay open.

        Side effect: Opens the circuit if ``opened_at`` is missing.
        """
        timeout = self._breaker.timeout_duration
        opened_at = await self._breaker.get_opened_at()
        if opened_at is None:
            await self._breaker.open()
            opened_at = await self._breaker.get_opened_at()
        if opened_at is None:
            opened_at = naive_utc_now()
        reopen = reopen_deadline(opened_at, timeout)
        if reopen is not None and naive_utc_now() < reopen:
            raise CircuitBreakerError(
                'Timeout not elapsed yet, circuit breaker still open',
                reopen,
            )


    async def call(self, func: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        """After the open window passes, move to HALF_OPEN and recurse through :meth:`CircuitBreaker.call`."""
        await self.before_call(func, *args, **kwargs)
        await self._breaker.half_open()
        return await self._breaker.call(func, *args, **kwargs)


class CircuitHalfOpenState(CircuitBreakerBaseState):
    """HALF_OPEN: one trial; success closes, failure re-opens."""

    def __init__(self, breaker: 'CircuitBreaker') -> None:
        super().__init__(breaker, CircuitBreakerState.HALF_OPEN)

    async def on_failure(self, exception: Exception) -> None:
        """Re-open the circuit after a failed trial.

        Raises:
            CircuitBreakerError: Always, chaining ``exception``.
        """
        await self._breaker.open()
        reopen = reopen_deadline(naive_utc_now(), self._breaker.timeout_duration)
        raise CircuitBreakerError(
            'Trial call failed, circuit breaker opened.',
            reopen,
        ) from exception

    async def on_success(self) -> None:
        """Close the circuit after a successful trial."""
        await self._breaker.close()


class CircuitBreakerState(Enum):
    """High-level circuit states; each member maps to a :class:`CircuitBreakerBaseState` subclass.

    Values:
        OPEN: :class:`CircuitOpenState`
        CLOSED: :class:`CircuitClosedState`
        HALF_OPEN: :class:`CircuitHalfOpenState`
    """

    OPEN = CircuitOpenState
    CLOSED = CircuitClosedState
    HALF_OPEN = CircuitHalfOpenState
