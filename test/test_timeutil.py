"""Tests for :mod:`asyncbreaker.timeutil` (single clock + OPEN-window math)."""

from datetime import datetime, timedelta

from pytest import mark

from asyncbreaker import timeutil


def test_naive_utc_now_returns_naive_utc_wall_time():
    t = timeutil.naive_utc_now()
    assert t.tzinfo is None
    assert isinstance(t, datetime)


def test_reopen_deadline_none_opened_at():
    assert timeutil.reopen_deadline(None, timedelta(seconds=1)) is None


def test_reopen_deadline_adds_timeout():
    opened = datetime(2024, 3, 1, 12, 0, 0)
    timeout = timedelta(minutes=2)
    assert timeutil.reopen_deadline(opened, timeout) == opened + timeout


def test_active_reopen_deadline_none_opened_at():
    assert timeutil.active_reopen_deadline(None, timedelta(seconds=1)) is None


def test_active_reopen_deadline_future_window(monkeypatch):
    frozen = datetime(2024, 3, 1, 12, 0, 0)
    monkeypatch.setattr(timeutil, 'naive_utc_now', lambda: frozen)
    opened = frozen - timedelta(seconds=30)
    timeout = timedelta(seconds=60)
    end = timeutil.active_reopen_deadline(opened, timeout)
    assert end == opened + timeout
    assert end > frozen


def test_active_reopen_deadline_elapsed_window_returns_none(monkeypatch):
    frozen = datetime(2024, 3, 1, 12, 0, 0)
    monkeypatch.setattr(timeutil, 'naive_utc_now', lambda: frozen)
    opened = frozen - timedelta(seconds=120)
    timeout = timedelta(seconds=60)
    assert timeutil.reopen_deadline(opened, timeout) < frozen
    assert timeutil.active_reopen_deadline(opened, timeout) is None


def test_active_reopen_deadline_boundary_not_active(monkeypatch):
    """When ``end == now``, the OPEN window is no longer *strictly* in the future."""
    frozen = datetime(2024, 3, 1, 12, 0, 0)
    monkeypatch.setattr(timeutil, 'naive_utc_now', lambda: frozen)
    opened = frozen - timedelta(seconds=60)
    timeout = timedelta(seconds=60)
    assert timeutil.reopen_deadline(opened, timeout) == frozen
    assert timeutil.active_reopen_deadline(opened, timeout) is None


def test_naive_utc_remaining_until_none():
    assert timeutil.naive_utc_remaining_until(None) == timedelta(0)


def test_naive_utc_remaining_until_past(monkeypatch):
    frozen = datetime(2024, 3, 1, 12, 0, 0)
    monkeypatch.setattr(timeutil, 'naive_utc_now', lambda: frozen)
    past = frozen - timedelta(seconds=1)
    assert timeutil.naive_utc_remaining_until(past) == timedelta(0)


def test_naive_utc_remaining_until_future(monkeypatch):
    frozen = datetime(2024, 3, 1, 12, 0, 0)
    monkeypatch.setattr(timeutil, 'naive_utc_now', lambda: frozen)
    future = frozen + timedelta(seconds=10)
    assert timeutil.naive_utc_remaining_until(future) == timedelta(seconds=10)


def test_posix_seconds_roundtrip_naive_utc():
    dt = datetime(2024, 6, 15, 10, 30, 45)
    sec = timeutil.naive_utc_to_posix_seconds(dt)
    back = timeutil.posix_seconds_to_naive_utc(sec)
    assert back == dt
    assert back.tzinfo is None


@mark.asyncio
async def test_sleep_for_remaining_noop_when_zero(monkeypatch):
    called = []

    async def fake_sleep(s):
        called.append(s)

    monkeypatch.setattr(timeutil.asyncio, 'sleep', fake_sleep)
    await timeutil.sleep_for_remaining(timedelta(0))
    assert called == []


@mark.asyncio
async def test_sleep_for_remaining_delegates_total_seconds(monkeypatch):
    called = []

    async def fake_sleep(s):
        called.append(s)

    monkeypatch.setattr(timeutil.asyncio, 'sleep', fake_sleep)
    await timeutil.sleep_for_remaining(timedelta(seconds=2, milliseconds=500))
    assert called == [2.5]
