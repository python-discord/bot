import functools
from collections import OrderedDict
from typing import Any, Callable


def async_cache(max_size: int = 128, arg_offset: int = 0) -> Callable:
    """
    LRU cache implementation for coroutines.

    Once the cache exceeds the maximum size, keys are deleted in FIFO order.

    An offset may be optionally provided to be applied to the coroutine's arguments when creating the cache key.
    """
    # Make global cache as dictionary to allow multiple function caches
    async_cache.cache = {}

    def decorator(function: Callable) -> Callable:
        """Define the async_cache decorator."""
        async_cache.cache[function.__name__] = OrderedDict()

        @functools.wraps(function)
        async def wrapper(*args) -> Any:
            """Decorator wrapper for the caching logic."""
            key = ':'.join(str(args[arg_offset:]))

            if key not in async_cache.cache:
                if len(async_cache.cache[function.__name__]) > max_size:
                    async_cache.cache[function.__name__].popitem(last=False)

                async_cache.cache[function.__name__][key] = await function(*args)
            return async_cache.cache[function.__name__][key]
        return wrapper
    return decorator
