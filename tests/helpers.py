import asyncio
import functools
from unittest.mock import MagicMock


__all__ = ('AsyncMock', 'async_test')


# TODO: Remove me on 3.8
# Allows you to mock a coroutine. Since the default `__call__` of `MagicMock`
# is not a coroutine, trying to mock a coroutine with it will result in errors
# as the default `__call__` is not awaitable. Use this class for monkeypatching
# coroutines instead.
class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)


def async_test(wrapped):
    """
    Run a test case via asyncio.

    Example:

        >>> @async_test
        ... async def lemon_wins():
        ...     assert True
    """

    @functools.wraps(wrapped)
    def wrapper(*args, **kwargs):
        return asyncio.run(wrapped(*args, **kwargs))
    return wrapper
