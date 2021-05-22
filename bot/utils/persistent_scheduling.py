import typing as t
from datetime import datetime, timedelta, timezone

import arrow
from arrow import Arrow
from async_rediscache import RedisCache

from bot.bot import Bot
from bot.utils.scheduling import Scheduler

SchedulerTaskFactory = t.Callable[[t.Union[str, int]], t.Coroutine[None, None, None]]
CacheKey = t.Union[str, int]


class PersistentScheduler:
    """
    Schedule the execution of coroutines and keep track of them even across restarts and cog reloads.

    When instantiating a PersistentScheduler, a name must be provided. This name is used to distinguish the
    instance's log messages and RedisCache from other instances. Using the name of the class or module containing
    the instance is suggested. The same name must be provided after a restart for the tasks to be preserved.

    A coroutine must be provided in order to reschedule each of the keys contained in the cache at init.
    The coroutine will take a single argument -- the ID that was used to create the Scheduler task in the first place.

    Coroutines can be scheduled with `schedule_at` or `schedule_later`.
    A unique ID is required to be given in order to keep track of the resulting Tasks.
    Any scheduled task can be cancelled prematurely using `cancel` by providing the same ID used to schedule it, but
    the task will be rescheduled from the cache on the next initialization. To remove the task completely, you can
    `delete` it.
    The `in` operator is supported for checking if a task with a given ID is currently scheduled.

    Any exception raised in a scheduled task is logged when the task is done.
    """

    def __init__(self, name: str, task_factory: SchedulerTaskFactory, bot: Bot):
        name = f"{__name__}.{name}"

        self._scheduler = Scheduler(name)
        self.cache = RedisCache(namespace=name)

        self.task_factory = task_factory
        self.bot = bot

        self._reschedule_task = self.bot.loop.create_task(self._start_scheduler())

    def __contains__(self, task_id: CacheKey) -> bool:
        """Return True if a task with the given `task_id` is currently scheduled."""
        return task_id in self._scheduler

    async def wait_until_ready(self) -> None:
        """Wait until the scheduler is ready and the cache is ready (and all cached tasks are scheduled)."""
        await self._reschedule_task

    async def get(self, task_id: CacheKey) -> t.Optional[Arrow]:
        """Get the time in which `task_id`'s task should go off. If the task is not found return None."""
        timestamp = await self.cache.get(task_id)

        if not timestamp:
            return None
        return Arrow.utcfromtimestamp(timestamp)

    async def to_dict(self) -> t.Dict[CacheKey, Arrow]:
        """
        Get a dict representation of the currently scheduled tasks.

        The dictionary contains the task_id's as keys, and the times in which the tasks should go off as values.
        """
        dict_ = await self.cache.to_dict()
        return {task_id: Arrow.utcfromtimestamp(timestamp) for task_id, timestamp in dict_.items()}

    async def reschedule_task(self, task_id: CacheKey) -> None:
        """Reschedule the task according to `task_factory` and `task_id`."""
        time = (await self.get(task_id)).datetime
        self._scheduler.schedule_at(time, task_id, coroutine=self._to_schedule(task_id))

    async def reschedule_all_tasks(self) -> None:
        """Reschedule all tasks according to `task_factory` and the ID's in the cache."""
        tasks = await self.cache.items()
        for task_id, timestamp in tasks:
            time = Arrow.utcfromtimestamp(timestamp)
            self._scheduler.schedule_at(time.datetime, task_id, coroutine=self._to_schedule(task_id))

    async def delete(self, task_id: CacheKey) -> None:
        """
        Unschedule the task identified by `task_id` and delete it from the cache.

        `cancel` is left as-is in order to be able to pause execution until the next reschedule.
        Log a warning if the task doesn't exist.
        """
        await self.cache.delete(task_id)

        self._scheduler.cancel(task_id)

    async def delete_all(self) -> None:
        """
        Unschedule all known tasks and wipe the cache.

        `cancel_all` remains untouched so that it can be used in instances such as cog unloads while preserving cache.
        """
        self._reschedule_task.cancel()
        await self.cache.clear()

        self._reschedule_task.add_done_callback(self._scheduler.cancel_all())

    async def schedule_at(self, time: datetime, task_id: CacheKey) -> None:
        """
        Schedule `coroutine` to be executed at the given `time` and add it to the cache.

        If `time` is timezone aware, then use that timezone to calculate now() when subtracting.
        If `time` is naïve, then use UTC.

        If `time` is in the past, schedule `coroutine` immediately.

        If a task with `task_id` already exists, close `coroutine` instead of scheduling it. This
        prevents unawaited coroutine warnings. Don't pass a coroutine that'll be re-used elsewhere.
        """
        self._scheduler.schedule_at(time, task_id, self._to_schedule(task_id))

        if time.tzinfo is None:
            time.replace(tzinfo=timezone.utc)
        await self.cache.set(task_id, time.timestamp())

    async def schedule_later(self, delay: t.Union[int, float], task_id: CacheKey) -> None:
        """
        Schedule `coroutine` to be executed after the given `delay` number of seconds and add it to the cache.

        If a task with `task_id` already exists, close `coroutine` instead of scheduling it. This
        prevents unawaited coroutine warnings. Don't pass a coroutine that'll be re-used elsewhere.
        """
        self._scheduler.schedule_later(delay, task_id, self._to_schedule(task_id))

        time = arrow.utcnow() + timedelta(seconds=delay)
        await self.cache.set(task_id, time.timestamp())

    def cancel_all(self) -> None:
        """Unschedule all known tasks."""
        self._reschedule_task.cancel()
        self._reschedule_task.add_done_callback(lambda _: self._scheduler.cancel_all())

    async def _start_scheduler(self) -> None:
        """Starts the persistent scheduler by awaiting the guild before rescheduling the tasks."""
        await self.bot.wait_until_guild_available()

        await self.reschedule_all_tasks()

    async def _to_schedule(self, task_id: CacheKey) -> None:
        """
        Wraps the task to run, so that we can delete the key from the cache.

        We delete the task from the cache first. If deletion fails for some reason the task will be run on
        the next load. If the task fails we don't care about rerunning it on the next load.
        """
        await self.cache.delete(task_id)

        await self.task_factory(task_id)
