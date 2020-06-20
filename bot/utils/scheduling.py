import asyncio
import contextlib
import logging
import typing as t
from functools import partial


class Scheduler:
    """Task scheduler."""

    def __init__(self, name: str):
        self.name = name

        self._log = logging.getLogger(f"{__name__}.{name}")
        self._scheduled_tasks: t.Dict[t.Hashable, asyncio.Task] = {}

    def __contains__(self, task_id: t.Hashable) -> bool:
        """Return True if a task with the given `task_id` is currently scheduled."""
        return task_id in self._scheduled_tasks

    def schedule_task(self, task_id: t.Hashable, task: t.Awaitable) -> None:
        """Schedule the execution of a task."""
        self._log.trace(f"Scheduling task #{task_id}...")

        if task_id in self._scheduled_tasks:
            self._log.debug(f"Did not schedule task #{task_id}; task was already scheduled.")
            return

        task = asyncio.create_task(task, name=f"{self.name}_{task_id}")
        task.add_done_callback(partial(self._task_done_callback, task_id))

        self._scheduled_tasks[task_id] = task
        self._log.debug(f"Scheduled task #{task_id} {id(task)}.")

    def cancel_task(self, task_id: t.Hashable, ignore_missing: bool = False) -> None:
        """
        Unschedule the task identified by `task_id`.

        If `ignore_missing` is True, a warning will not be sent if a task isn't found.
        """
        self._log.trace(f"Cancelling task #{task_id}...")
        task = self._scheduled_tasks.get(task_id)

        if not task:
            if not ignore_missing:
                self._log.warning(f"Failed to unschedule {task_id} (no task found).")
            return

        del self._scheduled_tasks[task_id]
        task.cancel()

        self._log.debug(f"Unscheduled task #{task_id} {id(task)}.")

    def cancel_all(self) -> None:
        """Unschedule all known tasks."""
        self._log.debug("Unscheduling all tasks")

        for task_id in self._scheduled_tasks.copy():
            self.cancel_task(task_id, ignore_missing=True)

    def _task_done_callback(self, task_id: t.Hashable, done_task: asyncio.Task) -> None:
        """
        Delete the task and raise its exception if one exists.

        If `done_task` and the task associated with `task_id` are different, then the latter
        will not be deleted. In this case, a new task was likely rescheduled with the same ID.
        """
        self._log.trace(f"Performing done callback for task #{task_id} {id(done_task)}.")

        scheduled_task = self._scheduled_tasks.get(task_id)

        if scheduled_task and done_task is scheduled_task:
            # A task for the ID exists and its the same as the done task.
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
