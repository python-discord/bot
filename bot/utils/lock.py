import inspect
import logging
from collections import defaultdict
from functools import partial, wraps
from typing import Any, Awaitable, Callable, Hashable, Union
from weakref import WeakValueDictionary

from bot.errors import LockedResourceError
from bot.utils import function

log = logging.getLogger(__name__)
__lock_dicts = defaultdict(WeakValueDictionary)

_IdCallableReturn = Union[Hashable, Awaitable[Hashable]]
_IdCallable = Callable[[function.BoundArgs], _IdCallableReturn]
ResourceId = Union[Hashable, _IdCallable]


class LockGuard:
    """
    A context manager which acquires and releases a lock (mutex).

    Raise RuntimeError if trying to acquire a locked lock.
    """

    def __init__(self):
        self._locked = False

    def locked(self) -> bool:
        """Return True if currently locked or False if unlocked."""
        return self._locked

    def __enter__(self):
        if self._locked:
            raise RuntimeError("Cannot acquire a locked lock.")

        self._locked = True

    def __exit__(self, _exc_type, _exc_value, _traceback):  # noqa: ANN001
        self._locked = False
        return False  # Indicate any raised exception shouldn't be suppressed.


def lock(namespace: Hashable, resource_id: ResourceId, *, raise_error: bool = False) -> Callable:
    """
    Turn the decorated coroutine function into a mutually exclusive operation on a `resource_id`.

    If any other mutually exclusive function currently holds the lock for a resource, do not run the
    decorated function and return None. If `raise_error` is True, raise `LockedResourceError` if
    the lock cannot be acquired.

    `namespace` is an identifier used to prevent collisions among resource IDs.

    `resource_id` identifies a resource on which to perform a mutually exclusive operation.
    It may also be a callable or awaitable which will return the resource ID given an ordered
    mapping of the parameters' names to arguments' values.

    If decorating a command, this decorator must go before (below) the `command` decorator.
    """
    def decorator(func: Callable) -> Callable:
        name = func.__name__

        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            log.trace(f"{name}: mutually exclusive decorator called")

            if callable(resource_id):
                log.trace(f"{name}: binding args to signature")
                bound_args = function.get_bound_args(func, args, kwargs)

                log.trace(f"{name}: calling the given callable to get the resource ID")
                id_ = resource_id(bound_args)

                if inspect.isawaitable(id_):
                    log.trace(f"{name}: awaiting to get resource ID")
                    id_ = await id_
            else:
                id_ = resource_id

            log.trace(f"{name}: getting lock for resource {id_!r} under namespace {namespace!r}")

            # Get the lock for the ID. Create a lock if one doesn't exist yet.
            locks = __lock_dicts[namespace]
            lock = locks.setdefault(id_, LockGuard())

            if not lock.locked():
                log.debug(f"{name}: resource {namespace!r}:{id_!r} is free; acquiring it...")
                with lock:
                    return await func(*args, **kwargs)
            else:
                log.info(f"{name}: aborted because resource {namespace!r}:{id_!r} is locked")
                if raise_error:
                    raise LockedResourceError(str(namespace), id_)

        return wrapper
    return decorator


def lock_arg(
    namespace: Hashable,
    name_or_pos: function.Argument,
    func: Callable[[Any], _IdCallableReturn] = None,
    *,
    raise_error: bool = False,
) -> Callable:
    """
    Apply the `lock` decorator using the value of the arg at the given name/position as the ID.

    `func` is an optional callable or awaitable which will return the ID given the argument value.
    See `lock` docs for more information.
    """
    decorator_func = partial(lock, namespace, raise_error=raise_error)
    return function.get_arg_value_wrapper(decorator_func, name_or_pos, func)
