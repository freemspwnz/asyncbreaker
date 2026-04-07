from datetime import timedelta

from pytest import mark, raises

from asyncbreaker import CircuitBreaker
from asyncbreaker.listener import CircuitBreakerListener
from asyncbreaker.state import CircuitBreakerState
from asyncbreaker.storage import CircuitMemoryStorage
from test.util import DummyException, func_succeed_async

pytestmark = mark.asyncio


async def test_default_state():
    for state in CircuitBreakerState:
        storage = CircuitMemoryStorage(state)
        breaker = CircuitBreaker(state_storage=storage)
        s = await breaker.fetch_state()
        assert isinstance(s, state.value)
        assert s.state == state


async def test_default_params():
    breaker = CircuitBreaker()

    assert 0 == await breaker.get_fail_counter()
    assert timedelta(seconds=60) == breaker.timeout_duration
    assert 5 == breaker.fail_max
    assert CircuitBreakerState.CLOSED == await breaker.get_current_state()
    assert () == breaker.excluded_exceptions
    assert () == breaker.listeners
    assert 'memory' == breaker.storage_name


async def test_new_with_custom_reset_timeout():
    breaker = CircuitBreaker(timeout_duration=timedelta(seconds=30))

    assert 0 == await breaker.get_fail_counter()
    assert timedelta(seconds=30) == breaker.timeout_duration
    assert 5 == breaker.fail_max
    assert () == breaker.excluded_exceptions
    assert () == breaker.listeners
    assert 'memory' == breaker.storage_name


async def test_new_with_custom_fail_max():
    breaker = CircuitBreaker(fail_max=10)
    assert 0 == await breaker.get_fail_counter()
    assert timedelta(seconds=60) == breaker.timeout_duration
    assert 10 == breaker.fail_max
    assert () == breaker.excluded_exceptions
    assert () == breaker.listeners
    assert 'memory' == breaker.storage_name


async def test_new_with_custom_excluded_exceptions():
    breaker = CircuitBreaker(exclude=[Exception])
    assert 0 == await breaker.get_fail_counter()
    assert timedelta(seconds=60) == breaker.timeout_duration
    assert 5 == breaker.fail_max
    assert (Exception,) == breaker.excluded_exceptions
    assert () == breaker.listeners
    assert 'memory' == breaker.storage_name


async def test_fail_max_setter():
    breaker = CircuitBreaker()

    assert 5 == breaker.fail_max
    breaker.fail_max = 10
    assert 10 == breaker.fail_max


async def test_reset_timeout_setter():
    breaker = CircuitBreaker()

    assert timedelta(seconds=60) == breaker.timeout_duration
    breaker.timeout_duration = timedelta(seconds=30)
    assert timedelta(seconds=30) == breaker.timeout_duration


async def test_call_with_no_args_async():
    breaker = CircuitBreaker()
    assert await breaker.call(func_succeed_async)


async def test_call_with_args_async():
    async def func(arg1, arg2):
        return arg1, arg2

    breaker = CircuitBreaker()
    assert (42, 'abc') == await breaker.call(func, 42, 'abc')


async def test_call_with_kwargs_async():
    async def func(**kwargs):
        return kwargs

    breaker = CircuitBreaker()
    kwargs = {'a': 1, 'b': 2}
    assert kwargs == await breaker.call(func, **kwargs)


async def test_add_listener():
    breaker = CircuitBreaker()

    assert () == breaker.listeners

    first = CircuitBreakerListener()
    breaker.add_listener(first)
    assert (first,) == breaker.listeners

    second = CircuitBreakerListener()
    breaker.add_listener(second)
    assert (first, second) == breaker.listeners


async def test_add_listeners():
    breaker = CircuitBreaker()

    first, second = CircuitBreakerListener(), CircuitBreakerListener()
    breaker.add_listeners(first, second)
    assert (first, second) == breaker.listeners


async def test_remove_listener():
    breaker = CircuitBreaker()

    first = CircuitBreakerListener()
    breaker.add_listener(first)
    assert (first,) == breaker.listeners

    breaker.remove_listener(first)
    assert () == breaker.listeners


async def test_excluded_exceptions():
    breaker = CircuitBreaker(
        exclude=[LookupError, lambda e: type(e) == DummyException and e.val == 3]
    )

    async def err_1():
        raise LookupError()

    async def err_2():
        raise DummyException()

    async def err_3():
        raise ValueError()

    async def err_4():
        raise DummyException(val=3)

    with raises(LookupError):
        await breaker.call(err_1)
    assert 0 == await breaker.get_fail_counter()

    with raises(DummyException):
        await breaker.call(err_2)
    assert 1 == await breaker.get_fail_counter()

    with raises(ValueError):
        await breaker.call(err_3)
    assert 2 == await breaker.get_fail_counter()

    with raises(DummyException):
        await breaker.call(err_4)
    assert 0 == await breaker.get_fail_counter()


async def test_add_excluded_exception():
    breaker = CircuitBreaker()

    assert () == breaker.excluded_exceptions

    breaker.add_excluded_exception(NotImplementedError)
    assert (NotImplementedError,) == breaker.excluded_exceptions

    breaker.add_excluded_exception(Exception)
    assert (NotImplementedError, Exception) == breaker.excluded_exceptions


async def test_add_excluded_exceptions():
    breaker = CircuitBreaker()

    breaker.add_excluded_exceptions(NotImplementedError, Exception)
    assert (NotImplementedError, Exception) == breaker.excluded_exceptions


async def test_remove_excluded_exception():
    breaker = CircuitBreaker()

    breaker.add_excluded_exception(NotImplementedError)
    assert (NotImplementedError,) == breaker.excluded_exceptions

    breaker.remove_excluded_exception(NotImplementedError)
    assert () == breaker.excluded_exceptions


async def test_decorator_variants():
    """``@breaker``, ``@breaker()``, and ``@breaker(ignore_on_call=True)`` behave the same for counts."""
    apply = (
        lambda br, fn: br(fn),
        lambda br, fn: br()(fn),
        lambda br, fn: br(ignore_on_call=True)(fn),
    )
    for wrap in apply:
        breaker = CircuitBreaker()
        suc = wrap(breaker, _decorated_suc)
        err = wrap(breaker, _decorated_err)

        assert 'Docstring' == suc.__doc__
        assert 'Docstring' == err.__doc__

        assert 0 == await breaker.get_fail_counter()

        with raises(DummyException):
            await err()

        assert 1 == await breaker.get_fail_counter()

        await suc()
        assert 0 == await breaker.get_fail_counter()


async def _decorated_suc():
    """Docstring"""
    pass


async def _decorated_err():
    """Docstring"""
    raise DummyException()


async def test_decorator_positional_arguments():
    breaker = CircuitBreaker()

    with raises(TypeError):

        @breaker(True)
        async def suc():
            """Docstring"""
            pass


async def test_decorator_rejects_sync_function():
    breaker = CircuitBreaker()

    with raises(TypeError):

        @breaker
        def sync_fn():
            pass


async def test_double_count():
    breaker = CircuitBreaker()

    @breaker
    async def err():
        """Docstring"""
        raise DummyException()

    assert 0 == await breaker.get_fail_counter()

    with raises(DummyException):
        await breaker.call(err)

    assert 1 == await breaker.get_fail_counter()


async def test_name():
    name = 'test_breaker'
    breaker = CircuitBreaker(name=name)
    assert breaker.name == name

    name = 'breaker_test'
    breaker.name = name
    assert breaker.name == name
