import asyncio
import contextlib
import logging
from abc import abstractmethod
from functools import partial
from typing import Dict

from bot.utils import CogABCMeta

log = logging.getLogger(__name__)


class Scheduler(metaclass=CogABCMeta):
    """Task scheduler."""

    def __init__(self):
        # Keep track of the child cog's name so the logs are clear.
        self.cog_name = self.__class__.__name__

        self._scheduled_tasks: Dict[str, asyncio.Task] = {}

    @abstractmethod
    async def _scheduled_task(self, task_object: dict) -> None:
        """
        A coroutine which handles the scheduling.

        This is added to the scheduled tasks, and should wait the task duration, execute the desired
        code, then clean up the task.

        For example, in Reminders this will wait for the reminder duration, send the reminder,
        then make a site API request to delete the reminder from the database.
        """

    def schedule_task(self, task_id: str, task_data: dict) -> None:
        """
        Schedules a task.

        `task_data` is passed to the `Scheduler._scheduled_task()` coroutine.
        """
        log.trace(f"{self.cog_name}: scheduling task #{task_id}...")

        if task_id in self._scheduled_tasks:
            log.debug(
                f"{self.cog_name}: did not schedule task #{task_id}; task was already scheduled."
            )
            return

        task = asyncio.create_task(self._scheduled_task(task_data))
        task.add_done_callback(partial(self._task_done_callback, task_id))

        self._scheduled_tasks[task_id] = task
        log.debug(f"{self.cog_name}: scheduled task #{task_id} {id(task)}.")

    def cancel_task(self, task_id: str) -> None:
        """Unschedule the task identified by `task_id`."""
        log.trace(f"{self.cog_name}: cancelling task #{task_id}...")
        task = self._scheduled_tasks.get(task_id)

        if not task:
            log.warning(f"{self.cog_name}: failed to unschedule {task_id} (no task found).")
            return

        task.cancel()
        del self._scheduled_tasks[task_id]

        log.debug(f"{self.cog_name}: unscheduled task #{task_id} {id(task)}.")

    def _task_done_callback(self, task_id: str, task: asyncio.Task) -> None:
        """
        Unschedule the task and raise its exception if one exists.

        If the task was cancelled, the CancelledError is retrieved and suppressed. In this case,
        the task is already assumed to have been unscheduled.
        """
        log.trace(f"{self.cog_name}: performing done callback for task #{task_id} {id(task)}")

        if task.cancelled():
            with contextlib.suppress(asyncio.CancelledError):
                task.exception()
        else:
            # Check if it exists to avoid logging a warning.
            if task_id in self._scheduled_tasks:
                # Only cancel if the task is not cancelled to avoid a race condition when a new
                # task is scheduled using the same ID. Reminders do this when re-scheduling after
                # editing.
                self.cancel_task(task_id)

            task.exception()
