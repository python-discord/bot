import functools
import logging
import typing as t

from bot.constants import DEBUG_MODE

log = logging.getLogger(__name__)


def mock_in_debug(return_value: t.Any) -> t.Callable:
    """
    Short-circuit function execution if in debug mode and return `return_value`.

    The original function name, and the incoming args and kwargs are DEBUG level logged
    upon each call. This is useful for expensive operations, i.e. media asset uploads
    that are prone to rate-limits but need to be tested extensively.
    """
    def decorator(func: t.Callable) -> t.Callable:
        @functools.wraps(func)
        async def wrapped(*args, **kwargs) -> t.Any:
            """Short-circuit and log if in debug mode."""
            if DEBUG_MODE:
                log.debug(f"Function {func.__name__} called with args: {args}, kwargs: {kwargs}")
                return return_value
            return await func(*args, **kwargs)
        return wrapped
    return decorator
