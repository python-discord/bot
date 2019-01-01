import asyncio
import contextlib
import logging
from abc import ABC, abstractmethod
from typing import Dict

log = logging.getLogger(__name__)


class Scheduler(ABC):

    def __init__(self):

        self.cog_name = self.__class__.__name__  # keep track of the child cog's name so the logs are clear.
        self.scheduled_tasks: Dict[str, asyncio.Task] = {}

    @abstractmethod
    async def _scheduled_task(self, task_object: dict):
        """
        A coroutine which handles the scheduling. This is added to the scheduled tasks,
        and should wait the task duration, execute the desired code, and clean up the task.
        For example, in Reminders this will wait for the reminder duration, send the reminder,
        then make a site API request to delete the reminder from the database.

        :param task_object:
        """

    def schedule_task(self, loop: asyncio.AbstractEventLoop, task_id: str, task_data: dict):
        """
        Schedules a task.
        :param loop: the asyncio event loop
        :param task_id: the ID of the task.
        :param task_data: the data of the task, passed to `Scheduler._scheduled_expiration`.
        """

        if task_id in self.scheduled_tasks:
            return

        task: asyncio.Task = create_task(loop, self._scheduled_task(task_data))

        self.scheduled_tasks[task_id] = task

    def cancel_task(self, task_id: str):
        """
        Un-schedules a task.
        :param task_id: the ID of the infraction in question
        """

        task = self.scheduled_tasks.get(task_id)

        if task is None:
            log.warning(f"{self.cog_name}: Failed to unschedule {task_id} (no task found).")
            return

        task.cancel()
        log.debug(f"{self.cog_name}: Unscheduled {task_id}.")
        del self.scheduled_tasks[task_id]


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
