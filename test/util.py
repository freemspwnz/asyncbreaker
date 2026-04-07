"""Async helpers and a test exception type for circuit breaker tests."""


class DummyException(Exception):
    """Configurable exception used as a *system* failure in tests."""

    def __init__(self, val: int = 0) -> None:
        """Create a dummy error with an optional discriminator ``val``."""
        self.val = val


async def func_succeed_async():
    """Async no-op that returns ``True``."""
    return True


async def func_exception_async():
    """Async call that always raises :class:`DummyException`."""
    raise DummyException()


def func_succeed_counted_async():
    """Return an async function that counts how many times it was awaited."""

    async def inner():
        inner.call_count += 1
        return True

    inner.call_count = 0
    return inner
