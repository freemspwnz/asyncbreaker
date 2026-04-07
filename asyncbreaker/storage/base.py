"""Abstract async storage for circuit breaker state and counters."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from ..state import CircuitBreakerState


class StorageError(Exception):
    """Raised when a storage backend cannot complete a read or write."""


class CircuitBreakerStorage(ABC):
    """Async persistence for circuit enum, failure counter, and ``opened_at`` timestamp."""

    def __init__(self, name: str) -> None:
        """Create storage with a display name.

        Args:
            name: Human-readable storage identifier (for example ``"memory"`` or ``"redis-async"``).
        """
        self._name = name

    @property
    def name(self) -> str:
        """Human-friendly name that identifies this storage."""
        return self._name

    @property
    @abstractmethod
    def constructor_state_hint(self) -> CircuitBreakerState:
        """Enum hint for synchronous breaker construction before ``await``.

        For remote backends this may be a initial state until the first :meth:`get_state` reflects
        the real value.

        Returns:
            A :class:`~asyncbreaker.state.CircuitBreakerState` member used to build the initial
            behavioral state object.
        """

    @abstractmethod
    async def get_state(self) -> CircuitBreakerState:
        """Return the current circuit state enum."""

    @abstractmethod
    async def increment_counter(self) -> None:
        """Increase the failure counter by one."""

    @abstractmethod
    async def reset_counter(self) -> None:
        """Reset the failure counter to zero."""

    @abstractmethod
    async def get_counter(self) -> int:
        """Return the current failure counter."""

    @abstractmethod
    async def get_opened_at(self) -> Optional[datetime]:
        """Return naive UTC time when the circuit was last opened, or ``None``.

        When the circuit is HALF_OPEN, implementations should clear ``opened_at`` so monitoring
        helpers that rely on it do not report a stale OPEN window.
        """

    @abstractmethod
    async def open_circuit(self, opened_at: datetime) -> None:
        """Set state to OPEN and record ``opened_at`` (naive UTC)."""

    @abstractmethod
    async def half_open_circuit(self) -> None:
        """Set state to HALF_OPEN and clear ``opened_at`` (trial allowed)."""

    @abstractmethod
    async def close_circuit(self) -> None:
        """Set state to CLOSED, reset the failure counter, and clear ``opened_at``."""
