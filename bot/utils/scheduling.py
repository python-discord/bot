import asyncio
import contextlib


def create_task(loop: asyncio.AbstractEventLoop, coro_or_future):
    """
    Creates an asyncio.Task object from a coroutine or future object.

    :param loop: the asyncio event loop.
    :param coro_or_future: the coroutine or future object to be scheduled.
    """

    task: asyncio.Task = asyncio.ensure_future(coro_or_future, loop=loop)

    # Silently ignore exceptions in a callback (handles the CancelledError nonsense)
    task.add_done_callback(_silent_exception)
    return task


def _silent_exception(future):
    with contextlib.suppress(Exception):
        future.exception()
