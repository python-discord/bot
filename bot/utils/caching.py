import functools
from collections import OrderedDict
from typing import Any, Callable


class AsyncCache:
    """
    LRU cache implementation for coroutines.

    Once the cache exceeds the maximum size, keys are deleted in FIFO order.

    An offset may be optionally provided to be applied to the coroutine's arguments when creating the cache key.
    """

    def __init__(self, max_size: int = 128):
        self._cache = OrderedDict()
        self._max_size = max_size

    def __call__(self, arg_offset: int = 0) -> Callable:
        """Decorator for async cache."""

        def decorator(function: Callable) -> Callable:
            """Define the async cache decorator."""

            @functools.wraps(function)
            async def wrapper(*args) -> Any:
                """Decorator wrapper for the caching logic."""
                key = args[arg_offset:]

                if key not in self._cache:
                    if len(self._cache) > self._max_size:
                        self._cache.popitem(last=False)

                    self._cache[key] = await function(*args)
                return self._cache[key]
            return wrapper
        return decorator

    def clear(self) -> None:
        """Clear cache instance."""
        self._cache.clear()
