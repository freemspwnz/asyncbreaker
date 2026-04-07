import asyncio
from asyncio import sleep
from datetime import datetime, timezone

from pytest import approx, mark, raises

from asyncbreaker import CircuitBreaker, CircuitBreakerError
from asyncbreaker.state import CircuitBreakerState
from asyncbreaker.storage import CircuitMemoryStorage
from test.util import DummyException, func_exception_async, func_succeed_async, func_succeed_counted_async

pytestmark = mark.asyncio


async def test_successful_call(async_storage):
    breaker = CircuitBreaker(state_storage=async_storage)
    assert await breaker.call(func_succeed_async)
    assert 0 == await breaker.get_fail_counter()
    assert CircuitBreakerState.CLOSED == await breaker.get_current_state()


async def test_one_failed_call(async_storage):
    breaker = CircuitBreaker(state_storage=async_storage)

    with raises(DummyException):
        await breaker.call(func_exception_async)

    assert 1 == await breaker.get_fail_counter()
    assert CircuitBreakerState.CLOSED == await breaker.get_current_state()


async def test_one_successful_call_after_failed_call(async_storage):
    breaker = CircuitBreaker(state_storage=async_storage)

    with raises(DummyException):
        await breaker.call(func_exception_async)

    assert 1 == await breaker.get_fail_counter()

    assert await breaker.call(func_succeed_async)
    assert 0 == await breaker.get_fail_counter()
    assert CircuitBreakerState.CLOSED == await breaker.get_current_state()


async def test_several_failed_calls(async_storage):
    breaker = CircuitBreaker(state_storage=async_storage, fail_max=3)

    with raises(DummyException):
        await breaker.call(func_exception_async)

    with raises(DummyException):
        await breaker.call(func_exception_async)

    with raises(CircuitBreakerError):
        await breaker.call(func_exception_async)

    assert await breaker.get_fail_counter() == 3
    assert await breaker.get_current_state() == CircuitBreakerState.OPEN


async def test_failed_call_after_timeout(async_storage, delta):
    breaker = CircuitBreaker(fail_max=3, timeout_duration=delta, state_storage=async_storage)

    with raises(DummyException):
        await breaker.call(func_exception_async)

    with raises(DummyException):
        await breaker.call(func_exception_async)

    assert CircuitBreakerState.CLOSED == await breaker.get_current_state()

    with raises(CircuitBreakerError):
        await breaker.call(func_exception_async)

    assert 3 == await breaker.get_fail_counter()

    await sleep(delta.total_seconds() * 2)

    with raises(CircuitBreakerError):
        await breaker.call(func_exception_async)

    assert 4 == await breaker.get_fail_counter()
    assert CircuitBreakerState.OPEN == await breaker.get_current_state()


async def test_successful_after_timeout(async_storage, delta):
    breaker = CircuitBreaker(fail_max=3, timeout_duration=delta, state_storage=async_storage)
    counted = func_succeed_counted_async()

    with raises(DummyException):
        await breaker.call(func_exception_async)

    with raises(DummyException):
        await breaker.call(func_exception_async)

    assert CircuitBreakerState.CLOSED == await breaker.get_current_state()

    with raises(CircuitBreakerError):
        await breaker.call(func_exception_async)

    assert CircuitBreakerState.OPEN == await breaker.get_current_state()

    with raises(CircuitBreakerError):
        await breaker.call(counted)

    assert 3 == await breaker.get_fail_counter()

    await sleep(delta.total_seconds() * 2)

    assert await breaker.call(counted)
    assert 0 == await breaker.get_fail_counter()
    assert CircuitBreakerState.CLOSED == await breaker.get_current_state()
    assert 1 == counted.call_count


async def test_successful_after_wait(async_storage, delta):
    breaker = CircuitBreaker(fail_max=1, timeout_duration=delta, state_storage=async_storage)
    counted = func_succeed_counted_async()

    try:
        await breaker.call(func_exception_async)
    except CircuitBreakerError:
        await asyncio.sleep(delta.total_seconds())

    await breaker.call(counted)
    assert counted.call_count == 1


async def test_failed_call_when_half_open(async_storage):
    breaker = CircuitBreaker(state_storage=async_storage)

    await breaker.half_open()
    assert 0 == await breaker.get_fail_counter()
    assert CircuitBreakerState.HALF_OPEN == await breaker.get_current_state()

    with raises(CircuitBreakerError):
        await breaker.call(func_exception_async)

    assert 1 == await breaker.get_fail_counter()
    assert CircuitBreakerState.OPEN == await breaker.get_current_state()


async def test_successful_call_when_half_open(async_storage):
    breaker = CircuitBreaker(state_storage=async_storage)

    await breaker.half_open()
    assert 0 == await breaker.get_fail_counter()
    assert CircuitBreakerState.HALF_OPEN == await breaker.get_current_state()

    assert await breaker.call(func_succeed_async)
    assert 0 == await breaker.get_fail_counter()
    assert CircuitBreakerState.CLOSED == await breaker.get_current_state()


async def test_close(async_storage):
    breaker = CircuitBreaker(fail_max=3, state_storage=async_storage)

    await breaker.open()
    assert 0 == await breaker.get_fail_counter()
    assert CircuitBreakerState.OPEN == await breaker.get_current_state()

    await breaker.close()
    assert 0 == await breaker.get_fail_counter()
    assert CircuitBreakerState.CLOSED == await breaker.get_current_state()


async def test_opened_at_cleared_when_half_open(async_storage):
    """HALF_OPEN storage clears ``opened_at`` so monitoring APIs do not show a stale OPEN window."""
    breaker = CircuitBreaker(state_storage=async_storage)
    await breaker.open()
    assert await async_storage.get_opened_at() is not None

    await breaker.half_open()
    assert await async_storage.get_opened_at() is None
    assert CircuitBreakerState.HALF_OPEN == await breaker.get_current_state()


async def test_compute_opens_at_none_in_half_open(async_storage, delta):
    """With no ``opened_at``, compute_opens_at / get_time_until_open are None."""
    breaker = CircuitBreaker(timeout_duration=delta, state_storage=async_storage)
    await breaker.open()
    await breaker.half_open()

    assert await breaker.get_opened_at() is None
    assert await breaker.compute_opens_at() is None
    assert await breaker.get_time_until_open() is None


async def test_reopen_time_matches_compute_opens_at_after_trip(async_storage, delta):
    """Exception :attr:`reopen_time` matches monitoring helpers that read storage."""
    breaker = CircuitBreaker(fail_max=1, timeout_duration=delta, state_storage=async_storage)
    with raises(CircuitBreakerError) as ei:
        await breaker.call(func_exception_async)
    assert ei.value.reopen_time == await breaker.compute_opens_at()
    tu = await breaker.get_time_until_open()
    assert tu is not None
    assert tu.total_seconds() == approx(ei.value.time_remaining.total_seconds(), abs=0.05)


async def test_reopen_time_matches_when_call_rejected_open(async_storage, delta):
    breaker = CircuitBreaker(fail_max=1, timeout_duration=delta, state_storage=async_storage)
    with raises(CircuitBreakerError):
        await breaker.call(func_exception_async)
    with raises(CircuitBreakerError) as ei:
        await breaker.call(func_succeed_async)
    assert ei.value.reopen_time == await breaker.compute_opens_at()


async def test_set_circuit_state_invalid_raises_value_error(async_storage):
    breaker = CircuitBreaker(state_storage=async_storage)

    with raises(ValueError, match='Invalid circuit state'):
        await breaker.set_circuit_state('not_an_enum')  # type: ignore[arg-type]

