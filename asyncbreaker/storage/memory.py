"""In-process async storage for a single :class:`~asyncbreaker.circuitbreaker.CircuitBreaker`."""

from datetime import datetime
from typing import Optional

from ..state import CircuitBreakerState

from .base import CircuitBreakerStorage


class CircuitMemoryStorage(CircuitBreakerStorage):
    """Async-compatible in-memory backend (no I/O; suitable for tests and single-process apps)."""

    def __init__(self, initial_state: CircuitBreakerState = CircuitBreakerState.CLOSED) -> None:
        """Create storage with the given initial circuit state.

        Args:
            initial_state: State until :meth:`open_circuit`, :meth:`half_open_circuit`, or
                :meth:`close_circuit` changes it.
        """
        super().__init__('memory')
        self._fail_counter = 0
        self._opened_at: Optional[datetime] = None
        self._circuit_state = initial_state

    @property
    def constructor_state_hint(self) -> CircuitBreakerState:
        """Initial enum value matching the current in-memory state."""
        return self._circuit_state

    async def get_state(self) -> CircuitBreakerState:
        """Return the current circuit state."""
        return self._circuit_state

    async def increment_counter(self) -> None:
        """Increase the failure counter by one."""
        self._fail_counter += 1

    async def reset_counter(self) -> None:
        """Reset the failure counter to zero."""
        self._fail_counter = 0

    async def get_counter(self) -> int:
        """Return the current failure counter."""
        return self._fail_counter

    async def get_opened_at(self) -> Optional[datetime]:
        """Return when the circuit was last opened (naive UTC), or ``None`` if not OPEN."""
        return self._opened_at

    async def open_circuit(self, opened_at: datetime) -> None:
        """Set OPEN and record ``opened_at``."""
        self._circuit_state = CircuitBreakerState.OPEN
        self._opened_at = opened_at

    async def half_open_circuit(self) -> None:
        """Set HALF_OPEN and clear ``opened_at``."""
        self._circuit_state = CircuitBreakerState.HALF_OPEN
        self._opened_at = None

    async def close_circuit(self) -> None:
        """Set CLOSED, reset the failure counter, and clear ``opened_at``."""
        self._circuit_state = CircuitBreakerState.CLOSED
        self._fail_counter = 0
        self._opened_at = None
