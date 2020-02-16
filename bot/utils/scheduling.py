import asyncio
import contextlib
import logging
from abc import abstractmethod
from typing import Dict

from bot.utils import CogABCMeta

log = logging.getLogger(__name__)


class Scheduler(metaclass=CogABCMeta):
    """Task scheduler."""

    def __init__(self):

        self.cog_name = self.__class__.__name__  # keep track of the child cog's name so the logs are clear.
        self.scheduled_tasks: Dict[str, asyncio.Task] = {}

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
        if task_id in self.scheduled_tasks:
            log.debug(
                f"{self.cog_name}: did not schedule task #{task_id}; task was already scheduled."
            )
            return

        task = asyncio.create_task(self._scheduled_task(task_data))
        task.add_done_callback(_suppress_cancelled_error)

        self.scheduled_tasks[task_id] = task
        log.debug(f"{self.cog_name}: scheduled task #{task_id}.")

    def cancel_task(self, task_id: str) -> None:
        """Un-schedules a task."""
        task = self.scheduled_tasks.get(task_id)

        if task is None:
            log.warning(f"{self.cog_name}: Failed to unschedule {task_id} (no task found).")
            return

        task.cancel()
        log.debug(f"{self.cog_name}: unscheduled task #{task_id}.")
        del self.scheduled_tasks[task_id]


def _suppress_cancelled_error(task: asyncio.Task) -> None:
    """Suppress a task's CancelledError exception."""
    if task.cancelled():
        with contextlib.suppress(asyncio.CancelledError):
            task.exception()
