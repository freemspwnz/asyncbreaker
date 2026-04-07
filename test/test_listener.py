from pytest import mark, raises

from asyncbreaker import CircuitBreaker
from asyncbreaker.listener import CircuitBreakerListener
from asyncbreaker.state import CircuitBreakerState
from test.util import DummyException, func_exception_async, func_succeed_async

pytestmark = mark.asyncio


async def test_transition_events(async_storage):
    class Listener(CircuitBreakerListener):
        def __init__(self):
            self.out = []

        async def state_change(self, breaker, old, new):
            assert breaker
            self.out.append((old.state, new.state))

    listener = Listener()
    breaker = CircuitBreaker(listeners=(listener,), state_storage=async_storage)
    assert CircuitBreakerState.CLOSED == await breaker.get_current_state()

    await breaker.open()
    assert CircuitBreakerState.OPEN == await breaker.get_current_state()

    await breaker.half_open()
    assert CircuitBreakerState.HALF_OPEN == await breaker.get_current_state()

    await breaker.close()
    assert CircuitBreakerState.CLOSED == await breaker.get_current_state()

    assert [
        (CircuitBreakerState.CLOSED, CircuitBreakerState.OPEN),
        (CircuitBreakerState.OPEN, CircuitBreakerState.HALF_OPEN),
        (CircuitBreakerState.HALF_OPEN, CircuitBreakerState.CLOSED),
    ] == listener.out


async def test_call_events(async_storage):
    class Listener(CircuitBreakerListener):
        def __init__(self):
            self.out = []

        async def before_call(self, breaker, func, *args, **kwargs):
            assert breaker
            self.out.append('CALL')

        async def success(self, breaker):
            assert breaker
            self.out.append('SUCCESS')

        async def failure(self, breaker, exception):
            assert breaker
            assert isinstance(exception, DummyException)
            self.out.append('FAILURE')

    listener = Listener()
    breaker = CircuitBreaker(listeners=(listener,), state_storage=async_storage)

    assert await breaker.call(func_succeed_async)

    with raises(DummyException):
        await breaker.call(func_exception_async)

    assert ['CALL', 'SUCCESS', 'CALL', 'FAILURE'] == listener.out
