"""
Async :class:`CircuitBreaker` facade and decorator.

This module wires user-facing configuration and lifecycle helpers to pluggable
:class:`~asyncbreaker.storage.base.CircuitBreakerStorage` and state objects from
:mod:`asyncbreaker.state`.
"""

import inspect
from datetime import timedelta, datetime
from functools import wraps
from typing import Any, Optional, Iterable, Callable, Type, List, Union, Awaitable, cast

from .listener import CircuitBreakerListener
from .state import CircuitBreakerState, CircuitBreakerBaseState
from .storage import CircuitMemoryStorage, CircuitBreakerStorage, StorageError
from .timeutil import (
    active_reopen_deadline,
    naive_utc_remaining_until,
    sleep_for_remaining,
    naive_utc_now,
)


class CircuitBreaker:
    """
    Async circuit breaker that guards coroutine calls via :meth:`call`.

    State and counters are stored in an async :class:`~asyncbreaker.storage.base.CircuitBreakerStorage`
    implementation (in-process memory by default). The breaker refreshes its cached behavioral
    state from storage before each guarded call so multiple processes can share Redis-backed
    storage.

    Attributes:
        fail_max (int): Number of consecutive system failures in CLOSED before opening.
        timeout_duration (timedelta): Window after OPEN before a trial (half-open) call is allowed.
        excluded_exceptions: Exception types or predicates that count as success, not failure.
        name: Optional label for logging or metrics.
    """

    def __init__(
        self,
        fail_max: int = 5,
        timeout_duration: Optional[timedelta] = None,
        exclude: Optional[Iterable[Union[Type[Exception], Callable[[Exception], object]]]] = None,
        listeners: Optional[Iterable[CircuitBreakerListener]] = None,
        state_storage: Optional[CircuitBreakerStorage] = None,
        name: Optional[str] = None,
    ) -> None:
        """Create a breaker with the given limits and storage.

        Args:
            fail_max: Failure threshold while CLOSED before tripping open. Defaults to ``5``.
            timeout_duration: Minimum time spent OPEN before a half-open trial. Defaults to
            60 seconds if omitted.
            exclude: Exception types (``issubclass``) or callables ``(exc) -> truthy`` that mark
            an error as *non-system* (treated like success for the counter).
            listeners: Objects implementing :class:`~asyncbreaker.listener.CircuitBreakerListener`.
            state_storage: Async persistence backend;
            defaults to :class:`~asyncbreaker.storage.memory.CircuitMemoryStorage`.
            name: Optional human-readable name.
        """
        self._state_storage = state_storage or CircuitMemoryStorage(CircuitBreakerState.CLOSED)
        initial = self._state_storage.constructor_state_hint
        self._state = initial.value(self)

        if fail_max < 1:
            raise ValueError(f'fail_max must be at least 1, got {fail_max}')
        self._fail_max = fail_max

        if timeout_duration is None:
            self._timeout_duration = timedelta(seconds=60)
        elif timeout_duration < timedelta(0):
            raise ValueError(f'timeout_duration must be a non-negative timedelta, got {timeout_duration}')
        else:
            self._timeout_duration = timeout_duration

        self._excluded_exceptions: List[Union[Type[Exception], Callable[[Exception], object]]] = list(exclude or [])
        self._listeners = list(listeners or [])
        self._name = name

    async def _notify_state_change(
        self,
        old: CircuitBreakerBaseState,
        new: CircuitBreakerBaseState,
    ) -> None:
        """Notify all listeners of a behavioral state object change.

        Args:
            old: Previous state wrapper instance.
            new: New state wrapper instance.
        """
        for listener in self.listeners:
            await listener.state_change(self, old, new)

    async def _persist_state(
        self,
        persist: Callable[[], Awaitable[None]],
        new_state: CircuitBreakerState,
        failure_message: str,
    ) -> None:
        try:
            await persist()
            prev = self._state
            self._state = new_state.value(self)
            await self._notify_state_change(prev, self._state)
        except StorageError as e:
            raise StorageError(failure_message) from e

    async def _refresh_state_from_storage(self) -> None:
        """Sync ``self._state`` from storage and notify if the enum value changed."""
        remote = await self._state_storage.get_state()
        if remote == self._state.state:
            return
        prev = self._state
        self._state = remote.value(self)
        await self._notify_state_change(prev, self._state)

    async def get_fail_counter(self) -> int:
        """Return the current failure counter from storage.

        Returns:
            Non-negative count of recorded system failures since the last reset.
        """
        return await self._state_storage.get_counter()

    async def get_opened_at(self) -> Optional[datetime]:
        """Return naive UTC ``opened_at`` from storage, or ``None`` if not set."""
        return await self._state_storage.get_opened_at()

    async def _increment_failure_counter(self) -> None:
        """Record one system failure in storage (used by state objects)."""
        await self._state_storage.increment_counter()

    async def _reset_failure_counter(self) -> None:
        """Clear the failure counter in storage (used by state objects)."""
        await self._state_storage.reset_counter()

    @property
    def storage_name(self) -> str:
        """Human-readable name of the configured storage backend (e.g. ``\"memory\"``)."""
        return self._state_storage.name

    @property
    def fail_max(self) -> int:
        """Maximum failures in CLOSED before opening the circuit."""
        return self._fail_max

    @fail_max.setter
    def fail_max(self, number: int) -> None:
        if number >= 1:
            self._fail_max = number
        else:
            raise ValueError(f'fail_max must be at least 1, got {number}')

    @property
    def timeout_duration(self) -> timedelta:
        """Duration the circuit stays OPEN before allowing a half-open trial."""
        return self._timeout_duration

    @timeout_duration.setter
    def timeout_duration(self, timeout: timedelta) -> None:
        if timeout < timedelta(0):
            raise ValueError(f'timeout_duration must be a non-negative timedelta, got {timeout}')
        self._timeout_duration = timeout

    async def compute_opens_at(self) -> Optional[datetime]:
        """Earliest UTC (naive) moment the OPEN window ends, if still applicable.

        Uses ``opened_at`` from storage plus :attr:`timeout_duration`. If the circuit is not
        effectively in an OPEN waiting window (e.g. CLOSED, or HALF_OPEN with ``opened_at``
        cleared), returns ``None``.

        Returns:
            Naive UTC datetime when the OPEN period ends, or ``None`` if there is no active
            open window to wait for.
        """
        opened = await self.get_opened_at()
        return active_reopen_deadline(opened, self.timeout_duration)

    async def get_time_until_open(self) -> Optional[timedelta]:
        """Remaining time until :meth:`compute_opens_at`, if any.

        Uses the same remaining-time calculation as :attr:`CircuitBreakerError.time_remaining`.

        Returns:
            Positive timedelta until the open window ends, or ``None`` if not waiting.
        """
        oa = await self.compute_opens_at()
        if oa is None:
            return None
        rem = naive_utc_remaining_until(oa)
        return rem or None

    async def sleep_until_open(self) -> None:
        """Sleep until the OPEN reset window passes (no-op if not applicable)."""
        oa = await self.compute_opens_at()
        if oa is None:
            return
        await sleep_for_remaining(naive_utc_remaining_until(oa))

    async def fetch_state(self) -> CircuitBreakerBaseState:
        """Refresh cached behavioral state from storage and return it.

        Returns:
            The current :class:`~asyncbreaker.state.CircuitBreakerBaseState` subclass instance
            used for the next :meth:`call`.
        """
        await self._refresh_state_from_storage()
        return self._state

    async def get_current_state(self) -> CircuitBreakerState:
        """Return the circuit enum from storage without necessarily updating listeners.

        Returns:
            :class:`~asyncbreaker.state.CircuitBreakerState` value read from storage.

        Note:
            Cached behavioral state may differ until :meth:`fetch_state` or :meth:`call` runs.
        """
        return await self._state_storage.get_state()

    @property
    def excluded_exceptions(self) -> tuple:
        """Configured exclusion types and predicates (immutable tuple view)."""
        return tuple(self._excluded_exceptions)

    def add_excluded_exception(self, exception: Union[Type[Exception], Callable[[Exception], object]]) -> None:
        """Append one exclusion rule.

        Args:
            exception: Exception class or callable returning truthy to exclude an error.
        """
        self._excluded_exceptions.append(exception)

    def add_excluded_exceptions(self, *exceptions: Union[Type[Exception], Callable[[Exception], object]]) -> None:
        """Append multiple exclusion rules."""
        for exc in exceptions:
            self.add_excluded_exception(exc)

    def remove_excluded_exception(self, exception: Union[Type[Exception], Callable[[Exception], object]]) -> None:
        """Remove a previously added exclusion rule if present."""
        if exception in self._excluded_exceptions:
            self._excluded_exceptions.remove(exception)

    def is_system_error(self, exception: Exception) -> bool:
        """Return whether ``exception`` counts as a system failure for the counter.

        Args:
            exception: Raised exception from a guarded call.

        Returns:
            ``False`` if the exception matches an excluded type or predicate; ``True`` otherwise.
        """
        exception_type = type(exception)
        for exclusion in self._excluded_exceptions:
            if type(exclusion) is type:
                if issubclass(exception_type, exclusion):
                    return False
            elif callable(exclusion):
                if exclusion(exception):
                    return False

        return True

    async def call(self, func: Callable[..., Awaitable[Any]], *args, **kwargs):
        """Run an async callable through the breaker (state machine + listeners).
        
        Automatic transitions that are part of handling this call (for example OPEN → HALF_OPEN
        after the timeout) complete before listener hooks run for the attempt that invokes ``func``.
        In states without such a transition, hooks follow the state's ``before_call`` as usual.

        Args:
            func: Async function to invoke.
            `*args`: Positional arguments for ``func``.
            `**kwargs`: Keyword arguments for ``func``.

        Returns:
            The awaitable result of ``func``.

        Raises:
            CircuitBreakerError: When the circuit is open or a state handler wraps the error.
            Exception: The original exception from ``func`` when counted as failure but not
            converted to :class:`~asyncbreaker.state.CircuitBreakerError`.
        """
        if getattr(cast(Any, func), '_ignore_on_call', False):
            return await func(*args, **kwargs)

        await self._refresh_state_from_storage()
        return await self._state.call(func, *args, **kwargs)

    async def open(self) -> None:
        """Force OPEN, set ``opened_at`` in storage, and refresh cached state.

        Raises:
            StorageError: If persistence fails (e.g. Redis unreachable).
        """
        await self._persist_state(
            lambda: self._state_storage.open_circuit(naive_utc_now()),
            CircuitBreakerState.OPEN,
            'Failed to open circuit due to storage unreachability',
        )

    async def half_open(self) -> None:
        """Force HALF_OPEN and clear ``opened_at`` in storage (trial allowed).

        Raises:
            StorageError: If persistence fails (e.g. Redis unreachable).
        """
        await self._persist_state(
            self._state_storage.half_open_circuit,
            CircuitBreakerState.HALF_OPEN,
            'Failed to half open circuit due to storage unreachability',
        )

    async def close(self) -> None:
        """Force CLOSED, reset failure counter, clear ``opened_at``.

        Raises:
            StorageError: If persistence fails (e.g. Redis unreachable).
        """
        await self._persist_state(
            self._state_storage.close_circuit,
            CircuitBreakerState.CLOSED,
            'Failed to close circuit due to storage unreachability',
        )

    async def set_circuit_state(self, state: CircuitBreakerState) -> None:
        """Persist the given enum to storage and replace the cached behavioral state.

        Args:
            state: Target :class:`~asyncbreaker.state.CircuitBreakerState`.

        Raises:
            ValueError: If ``state`` is not a known member (should not occur for normal enum use).
            StorageError: On storage failures from the delegated ``open`` / ``close`` / ``half_open``.
        """
        if state == CircuitBreakerState.OPEN:
            await self.open()
        elif state == CircuitBreakerState.CLOSED:
            await self.close()
        elif state == CircuitBreakerState.HALF_OPEN:
            await self.half_open()
        else:
            raise ValueError(f'Invalid circuit state: {state}')

    def __call__(self, *call_args, ignore_on_call=True):
        """Decorator factory: ``@breaker`` or ``@breaker(ignore_on_call=False)``.

        Args:
            `*call_args`: Either empty (return decorator) or a single function for ``@breaker(fn)``.
            ignore_on_call: When ``True`` (default), wrappers set ``_ignore_on_call`` so nested
            ``call(wrapper)`` does not double-apply the breaker.

        Returns:
            Async wrapper around the decorated function.

        Raises:
            TypeError: If the decorated callable is not a coroutine function, or if invalid
            positional arguments are passed to the factory.
        """
        def _outer_wrapper(func):
            if not inspect.iscoroutinefunction(func):
                raise TypeError('CircuitBreaker decorator only supports async functions')

            @wraps(func)
            async def _inner_wrapper(*args, **kwargs):
                return await self.call(func, *args, **kwargs)

            setattr(_inner_wrapper, '_ignore_on_call', ignore_on_call)
            return _inner_wrapper

        if len(call_args) == 1 and inspect.iscoroutinefunction(call_args[0]):
            return _outer_wrapper(*call_args)
        if len(call_args) == 0:
            return _outer_wrapper
        raise TypeError('Decorator does not accept positional arguments.')

    @property
    def listeners(self) -> tuple:
        """Registered listeners as an immutable tuple."""
        return tuple(self._listeners)

    def add_listener(self, listener: CircuitBreakerListener) -> None:
        """Register a listener instance."""
        self._listeners.append(listener)

    def add_listeners(self, *listeners: CircuitBreakerListener) -> None:
        """Register several listeners."""
        for listener in listeners:
            self.add_listener(listener)

    def remove_listener(self, listener: CircuitBreakerListener) -> None:
        """Remove a listener if it is registered."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    @property
    def name(self) -> Optional[str]:
        """Optional breaker name."""
        return self._name

    @name.setter
    def name(self, name: str) -> None:
        self._name = name
