"""Wall-clock and OPEN-window time math (naive UTC).

All circuit-breaker time comparisons and Redis epoch conversions should go through this module
so behavior stays consistent when the clock or formulas change.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional


def naive_utc_now() -> datetime:
    """Current instant as naive UTC (matches stored ``opened_at`` conventions)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def reopen_deadline(opened_at: Optional[datetime], timeout: timedelta) -> Optional[datetime]:
    """When the OPEN reset window ends (half-open trial allowed). ``None`` if no open timestamp."""
    if opened_at is None:
        return None
    return opened_at + timeout


def active_reopen_deadline(opened_at: Optional[datetime], timeout: timedelta) -> Optional[datetime]:
    """Deadline from :func:`reopen_deadline` only while still strictly in the future.

    Used for monitoring helpers: once the window has elapsed, returns ``None`` even if storage
    still says OPEN until the next :meth:`~asyncbreaker.circuitbreaker.CircuitBreaker.call`.
    """
    end = reopen_deadline(opened_at, timeout)
    if end is None:
        return None
    if end <= naive_utc_now():
        return None
    return end


def naive_utc_remaining_until(opens_at: Optional[datetime]) -> timedelta:
    """Non-negative time until ``opens_at``, or zero if ``None`` or already passed."""
    if opens_at is None:
        return timedelta(0)
    return max(timedelta(0), opens_at - naive_utc_now())


async def sleep_for_remaining(remaining: timedelta) -> None:
    """``asyncio.sleep`` for ``remaining`` when positive (no-op otherwise)."""
    if remaining > timedelta(0):
        await asyncio.sleep(remaining.total_seconds())


def naive_utc_to_posix_seconds(ts: datetime) -> float:
    """Treat naive *ts* as UTC wall time (Redis ``opened_at`` write path)."""
    return ts.replace(tzinfo=timezone.utc).timestamp()


def posix_seconds_to_naive_utc(ts: float) -> datetime:
    """Epoch seconds to naive UTC (Redis ``opened_at`` read path)."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
