import functools
from collections import OrderedDict
from typing import Any, Callable


def async_cache(max_size: int = 128, arg_offset: int = 0) -> Callable:
    """
    LRU cache implementation for coroutines.

    Once the cache exceeds the maximum size, keys are deleted in FIFO order.

    An offset may be optionally provided to be applied to the coroutine's arguments when creating the cache key.
    """
    # Assign the cache to the function itself so we can clear it from outside.
    async_cache.cache = OrderedDict()

    def decorator(function: Callable) -> Callable:
        """Define the async_cache decorator."""
        @functools.wraps(function)
        async def wrapper(*args) -> Any:
            """Decorator wrapper for the caching logic."""
            key = ':'.join(args[arg_offset:])

            value = async_cache.cache.get(key)
            if value is None:
                if len(async_cache.cache) > max_size:
                    async_cache.cache.popitem(last=False)

                async_cache.cache[key] = await function(*args)
            return async_cache.cache[key]
        return wrapper
    return decorator
