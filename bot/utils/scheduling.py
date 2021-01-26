import asyncio
import contextlib
import inspect
import logging
import typing as t
from datetime import datetime
from functools import partial


class Scheduler:
    """
    Schedule the execution of coroutines and keep track of them.

    When instantiating a Scheduler, a name must be provided. This name is used to distinguish the
    instance's log messages from other instances. Using the name of the class or module containing
    the instance is suggested.

    Coroutines can be scheduled immediately with `schedule` or in the future with `schedule_at`
    or `schedule_later`. A unique ID is required to be given in order to keep track of the
    resulting Tasks. Any scheduled task can be cancelled prematurely using `cancel` by providing
    the same ID used to schedule it.  The `in` operator is supported for checking if a task with a
    given ID is currently scheduled.

    Any exception raised in a scheduled task is logged when the task is done.
    """

    def __init__(self, name: str):
        self.name = name

        self._log = logging.getLogger(f"{__name__}.{name}")
        self._scheduled_tasks: t.Dict[t.Hashable, asyncio.Task] = {}

    def __contains__(self, task_id: t.Hashable) -> bool:
        """Return True if a task with the given `task_id` is currently scheduled."""
        return task_id in self._scheduled_tasks

    def schedule(self, task_id: t.Hashable, coroutine: t.Coroutine) -> None:
        """
        Schedule the execution of a `coroutine`.

        If a task with `task_id` already exists, close `coroutine` instead of scheduling it. This
        prevents unawaited coroutine warnings. Don't pass a coroutine that'll be re-used elsewhere.
        """
        self._log.trace(f"Scheduling task #{task_id}...")

        msg = f"Cannot schedule an already started coroutine for #{task_id}"
        assert inspect.getcoroutinestate(coroutine) == "CORO_CREATED", msg

        if task_id in self._scheduled_tasks:
            self._log.debug(f"Did not schedule task #{task_id}; task was already scheduled.")
            coroutine.close()
            return

        task = asyncio.create_task(coroutine, name=f"{self.name}_{task_id}")
        task.add_done_callback(partial(self._task_done_callback, task_id))

        self._scheduled_tasks[task_id] = task
        self._log.debug(f"Scheduled task #{task_id} {id(task)}.")

    def schedule_at(self, time: datetime, task_id: t.Hashable, coroutine: t.Coroutine) -> None:
        """
        Schedule `coroutine` to be executed at the given naïve UTC `time`.

        If `time` is in the past, schedule `coroutine` immediately.

        If a task with `task_id` already exists, close `coroutine` instead of scheduling it. This
        prevents unawaited coroutine warnings. Don't pass a coroutine that'll be re-used elsewhere.
        """
        delay = (time - datetime.utcnow()).total_seconds()
        if delay > 0:
            coroutine = self._await_later(delay, task_id, coroutine)

        self.schedule(task_id, coroutine)

    def schedule_later(self, delay: t.Union[int, float], task_id: t.Hashable, coroutine: t.Coroutine) -> None:
        """
        Schedule `coroutine` to be executed after the given `delay` number of seconds.

        If a task with `task_id` already exists, close `coroutine` instead of scheduling it. This
        prevents unawaited coroutine warnings. Don't pass a coroutine that'll be re-used elsewhere.
        """
        self.schedule(task_id, self._await_later(delay, task_id, coroutine))

    def cancel(self, task_id: t.Hashable) -> None:
        """Unschedule the task identified by `task_id`. Log a warning if the task doesn't exist."""
        self._log.trace(f"Cancelling task #{task_id}...")

        try:
            task = self._scheduled_tasks.pop(task_id)
        except KeyError:
            self._log.warning(f"Failed to unschedule {task_id} (no task found).")
        else:
            task.cancel()

            self._log.debug(f"Unscheduled task #{task_id} {id(task)}.")

    def cancel_all(self) -> None:
        """Unschedule all known tasks."""
        self._log.debug("Unscheduling all tasks")

        for task_id in self._scheduled_tasks.copy():
            self.cancel(task_id)

    async def _await_later(self, delay: t.Union[int, float], task_id: t.Hashable, coroutine: t.Coroutine) -> None:
        """Await `coroutine` after the given `delay` number of seconds."""
        try:
            self._log.trace(f"Waiting {delay} seconds before awaiting coroutine for #{task_id}.")
            await asyncio.sleep(delay)

            # Use asyncio.shield to prevent the coroutine from cancelling itself.
            self._log.trace(f"Done waiting for #{task_id}; now awaiting the coroutine.")
            await asyncio.shield(coroutine)
        finally:
            # Close it to prevent unawaited coroutine warnings,
            # which would happen if the task was cancelled during the sleep.
            # Only close it if it's not been awaited yet. This check is important because the
            # coroutine may cancel this task, which would also trigger the finally block.
            state = inspect.getcoroutinestate(coroutine)
            if state == "CORO_CREATED":
                self._log.debug(f"Explicitly closing the coroutine for #{task_id}.")
                coroutine.close()
            else:
                self._log.debug(f"Finally block reached for #{task_id}; {state=}")

    def _task_done_callback(self, task_id: t.Hashable, done_task: asyncio.Task) -> None:
        """
        Delete the task and raise its exception if one exists.

        If `done_task` and the task associated with `task_id` are different, then the latter
        will not be deleted. In this case, a new task was likely rescheduled with the same ID.
        """
        self._log.trace(f"Performing done callback for task #{task_id} {id(done_task)}.")

        scheduled_task = self._scheduled_tasks.get(task_id)

        if scheduled_task and done_task is scheduled_task:
            # A task for the ID exists and is the same as the done task.
            # Since this is the done callback, the task is already done so no need to cancel it.
            self._log.trace(f"Deleting task #{task_id} {id(done_task)}.")
            del self._scheduled_tasks[task_id]
        elif scheduled_task:
            # A new task was likely rescheduled with the same ID.
            self._log.debug(
                f"The scheduled task #{task_id} {id(scheduled_task)} "
                f"and the done task {id(done_task)} differ."
            )
        elif not done_task.cancelled():
            self._log.warning(
                f"Task #{task_id} not found while handling task {id(done_task)}! "
                f"A task somehow got unscheduled improperly (i.e. deleted but not cancelled)."
            )

        with contextlib.suppress(asyncio.CancelledError):
            exception = done_task.exception()
            # Log the exception if one exists.
            if exception:
                self._log.error(f"Error in task #{task_id} {id(done_task)}!", exc_info=exception)


def create_task(*args, **kwargs) -> asyncio.Task:
    """Wrapper for `asyncio.create_task` which logs exceptions raised in the task."""
    task = asyncio.create_task(*args, **kwargs)
    task.add_done_callback(_log_task_exception)
    return task


def _log_task_exception(task: asyncio.Task) -> None:
    """Retrieve and log the exception raised in `task` if one exists."""
    with contextlib.suppress(asyncio.CancelledError):
        exception = task.exception()
        # Log the exception if one exists.
        if exception:
            log = logging.getLogger(__name__)
            log.error(f"Error in task {task.get_name()} {id(task)}!", exc_info=exception)
