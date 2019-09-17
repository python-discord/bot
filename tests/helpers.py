import asyncio
import functools
from unittest.mock import MagicMock


__all__ = ('AsyncMock', 'async_test')


# TODO: Remove me on 3.8
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
