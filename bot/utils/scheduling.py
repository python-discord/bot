import asyncio
import contextlib
import logging
import typing as t
from abc import abstractmethod
from functools import partial

from bot.utils import CogABCMeta


class Scheduler(metaclass=CogABCMeta):
    """Task scheduler."""

    def __init__(self, name: str):
        self.name = name

        self._log = logging.getLogger(f"{__name__}.{name}")
        self._scheduled_tasks: t.Dict[t.Hashable, asyncio.Task] = {}

    @abstractmethod
    async def _scheduled_task(self, task_object: t.Any) -> None:
        """
        A coroutine which handles the scheduling.

        This is added to the scheduled tasks, and should wait the task duration, execute the desired
        code, then clean up the task.

        For example, in Reminders this will wait for the reminder duration, send the reminder,
        then make a site API request to delete the reminder from the database.
        """

    def schedule_task(self, task_id: t.Hashable, task_data: t.Any) -> None:
        """
        Schedules a task.

        `task_data` is passed to the `Scheduler._scheduled_task()` coroutine.
        """
        self._log.trace(f"Scheduling task #{task_id}...")

        if task_id in self._scheduled_tasks:
            self._log.debug(f"Did not schedule task #{task_id}; task was already scheduled.")
            return

        task = asyncio.create_task(self._scheduled_task(task_data))
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
