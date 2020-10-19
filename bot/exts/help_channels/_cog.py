import asyncio
import logging
import random
import typing as t
from datetime import datetime, timezone

import discord
import discord.abc
from async_rediscache import RedisCache
from discord.ext import commands

from bot import constants
from bot.bot import Bot
from bot.exts.help_channels import _channel, _message
from bot.exts.help_channels._name import create_name_queue
from bot.utils import channel as channel_utils
from bot.utils.scheduling import Scheduler

log = logging.getLogger(__name__)

HELP_CHANNEL_TOPIC = """
This is a Python help channel. You can claim your own help channel in the Python Help: Available category.
"""

CoroutineFunc = t.Callable[..., t.Coroutine]


class HelpChannels(commands.Cog):
    """
    Manage the help channel system of the guild.

    The system is based on a 3-category system:

    Available Category

    * Contains channels which are ready to be occupied by someone who needs help
    * Will always contain `constants.HelpChannels.max_available` channels; refilled automatically
      from the pool of dormant channels
        * Prioritise using the channels which have been dormant for the longest amount of time
        * If there are no more dormant channels, the bot will automatically create a new one
        * If there are no dormant channels to move, helpers will be notified (see `notify()`)
    * When a channel becomes available, the dormant embed will be edited to show `AVAILABLE_MSG`
    * User can only claim a channel at an interval `constants.HelpChannels.claim_minutes`
        * To keep track of cooldowns, user which claimed a channel will have a temporary role

    In Use Category

    * Contains all channels which are occupied by someone needing help
    * Channel moves to dormant category after `constants.HelpChannels.idle_minutes` of being idle
    * Command can prematurely mark a channel as dormant
        * Channel claimant is allowed to use the command
        * Allowed roles for the command are configurable with `constants.HelpChannels.cmd_whitelist`
    * When a channel becomes dormant, an embed with `DORMANT_MSG` will be sent

    Dormant Category

    * Contains channels which aren't in use
    * Channels are used to refill the Available category

    Help channels are named after the chemical elements in `bot/resources/elements.json`.
    """

    # This cache tracks which channels are claimed by which members.
    # RedisCache[discord.TextChannel.id, t.Union[discord.User.id, discord.Member.id]]
    help_channel_claimants = RedisCache()

    # This dictionary maps a help channel to the time it was claimed
    # RedisCache[discord.TextChannel.id, UtcPosixTimestamp]
    claim_times = RedisCache()

    def __init__(self, bot: Bot):
        self.bot = bot
        self.scheduler = Scheduler(self.__class__.__name__)

        # Categories
        self.available_category: discord.CategoryChannel = None
        self.in_use_category: discord.CategoryChannel = None
        self.dormant_category: discord.CategoryChannel = None

        # Queues
        self.channel_queue: asyncio.Queue[discord.TextChannel] = None
        self.name_queue: t.Deque[str] = None

        self.last_notification: t.Optional[datetime] = None

        # Asyncio stuff
        self.queue_tasks: t.List[asyncio.Task] = []
        self.ready = asyncio.Event()
        self.on_message_lock = asyncio.Lock()
        self.init_task = self.bot.loop.create_task(self.init_cog())

    def cog_unload(self) -> None:
        """Cancel the init task and scheduled tasks when the cog unloads."""
        log.trace("Cog unload: cancelling the init_cog task")
        self.init_task.cancel()

        log.trace("Cog unload: cancelling the channel queue tasks")
        for task in self.queue_tasks:
            task.cancel()

        self.scheduler.cancel_all()

    def create_channel_queue(self) -> asyncio.Queue:
        """
        Return a queue of dormant channels to use for getting the next available channel.

        The channels are added to the queue in a random order.
        """
        log.trace("Creating the channel queue.")

        channels = list(_channel.get_category_channels(self.dormant_category))
        random.shuffle(channels)

        log.trace("Populating the channel queue with channels.")
        queue = asyncio.Queue()
        for channel in channels:
            queue.put_nowait(channel)

        return queue

    async def create_dormant(self) -> t.Optional[discord.TextChannel]:
        """
        Create and return a new channel in the Dormant category.

        The new channel will sync its permission overwrites with the category.

        Return None if no more channel names are available.
        """
        log.trace("Getting a name for a new dormant channel.")

        try:
            name = self.name_queue.popleft()
        except IndexError:
            log.debug("No more names available for new dormant channels.")
            return None

        log.debug(f"Creating a new dormant channel named {name}.")
        return await self.dormant_category.create_text_channel(name, topic=HELP_CHANNEL_TOPIC)

    async def dormant_check(self, ctx: commands.Context) -> bool:
        """Return True if the user is the help channel claimant or passes the role check."""
        if await self.help_channel_claimants.get(ctx.channel.id) == ctx.author.id:
            log.trace(f"{ctx.author} is the help channel claimant, passing the check for dormant.")
            self.bot.stats.incr("help.dormant_invoke.claimant")
            return True

        log.trace(f"{ctx.author} is not the help channel claimant, checking roles.")
        has_role = await commands.has_any_role(*constants.HelpChannels.cmd_whitelist).predicate(ctx)

        if has_role:
            self.bot.stats.incr("help.dormant_invoke.staff")

        return has_role

    @commands.command(name="close", aliases=["dormant", "solved"], enabled=False)
    async def close_command(self, ctx: commands.Context) -> None:
        """
        Make the current in-use help channel dormant.

        Make the channel dormant if the user passes the `dormant_check`,
        delete the message that invoked this,
        and reset the send permissions cooldown for the user who started the session.
        """
        log.trace("close command invoked; checking if the channel is in-use.")
        if ctx.channel.category == self.in_use_category:
            if await self.dormant_check(ctx):
                await self.remove_cooldown_role(ctx.author)

                # Ignore missing task when cooldown has passed but the channel still isn't dormant.
                if ctx.author.id in self.scheduler:
                    self.scheduler.cancel(ctx.author.id)

                await self.move_to_dormant(ctx.channel, "command")
                self.scheduler.cancel(ctx.channel.id)
        else:
            log.debug(f"{ctx.author} invoked command 'dormant' outside an in-use help channel")

    async def get_available_candidate(self) -> discord.TextChannel:
        """
        Return a dormant channel to turn into an available channel.

        If no channel is available, wait indefinitely until one becomes available.
        """
        log.trace("Getting an available channel candidate.")

        try:
            channel = self.channel_queue.get_nowait()
        except asyncio.QueueEmpty:
            log.info("No candidate channels in the queue; creating a new channel.")
            channel = await self.create_dormant()

            if not channel:
                log.info("Couldn't create a candidate channel; waiting to get one from the queue.")
                notify_channel = self.bot.get_channel(constants.HelpChannels.notify_channel)
                last_notification = await _message.notify(notify_channel, self.last_notification)
                if last_notification:
                    self.last_notification = last_notification
                    self.bot.stats.incr("help.out_of_channel_alerts")

                channel = await self.wait_for_dormant_channel()

        return channel

    async def init_available(self) -> None:
        """Initialise the Available category with channels."""
        log.trace("Initialising the Available category with channels.")

        channels = list(_channel.get_category_channels(self.available_category))
        missing = constants.HelpChannels.max_available - len(channels)

        # If we've got less than `max_available` channel available, we should add some.
        if missing > 0:
            log.trace(f"Moving {missing} missing channels to the Available category.")
            for _ in range(missing):
                await self.move_to_available()

        # If for some reason we have more than `max_available` channels available,
        # we should move the superfluous ones over to dormant.
        elif missing < 0:
            log.trace(f"Moving {abs(missing)} superfluous available channels over to the Dormant category.")
            for channel in channels[:abs(missing)]:
                await self.move_to_dormant(channel, "auto")

    async def init_categories(self) -> None:
        """Get the help category objects. Remove the cog if retrieval fails."""
        log.trace("Getting the CategoryChannel objects for the help categories.")

        try:
            self.available_category = await channel_utils.try_get_channel(
                constants.Categories.help_available
            )
            self.in_use_category = await channel_utils.try_get_channel(
                constants.Categories.help_in_use
            )
            self.dormant_category = await channel_utils.try_get_channel(
                constants.Categories.help_dormant
            )
        except discord.HTTPException:
            log.exception("Failed to get a category; cog will be removed")
            self.bot.remove_cog(self.qualified_name)

    async def init_cog(self) -> None:
        """Initialise the help channel system."""
        log.trace("Waiting for the guild to be available before initialisation.")
        await self.bot.wait_until_guild_available()

        log.trace("Initialising the cog.")
        await self.init_categories()
        await self.check_cooldowns()

        self.channel_queue = self.create_channel_queue()
        self.name_queue = create_name_queue(
            self.available_category,
            self.in_use_category,
            self.dormant_category,
        )

        log.trace("Moving or rescheduling in-use channels.")
        for channel in _channel.get_category_channels(self.in_use_category):
            await self.move_idle_channel(channel, has_task=False)

        # Prevent the command from being used until ready.
        # The ready event wasn't used because channels could change categories between the time
        # the command is invoked and the cog is ready (e.g. if move_idle_channel wasn't called yet).
        # This may confuse users. So would potentially long delays for the cog to become ready.
        self.close_command.enabled = True

        await self.init_available()

        log.info("Cog is ready!")
        self.ready.set()

        self.report_stats()

    def report_stats(self) -> None:
        """Report the channel count stats."""
        total_in_use = sum(1 for _ in _channel.get_category_channels(self.in_use_category))
        total_available = sum(1 for _ in _channel.get_category_channels(self.available_category))
        total_dormant = sum(1 for _ in _channel.get_category_channels(self.dormant_category))

        self.bot.stats.gauge("help.total.in_use", total_in_use)
        self.bot.stats.gauge("help.total.available", total_available)
        self.bot.stats.gauge("help.total.dormant", total_dormant)

    @staticmethod
    def is_claimant(member: discord.Member) -> bool:
        """Return True if `member` has the 'Help Cooldown' role."""
        return any(constants.Roles.help_cooldown == role.id for role in member.roles)

    async def move_idle_channel(self, channel: discord.TextChannel, has_task: bool = True) -> None:
        """
        Make the `channel` dormant if idle or schedule the move if still active.

        If `has_task` is True and rescheduling is required, the extant task to make the channel
        dormant will first be cancelled.
        """
        log.trace(f"Handling in-use channel #{channel} ({channel.id}).")

        if not await _message.is_empty(channel):
            idle_seconds = constants.HelpChannels.idle_minutes * 60
        else:
            idle_seconds = constants.HelpChannels.deleted_idle_minutes * 60

        time_elapsed = await _channel.get_idle_time(channel)

        if time_elapsed is None or time_elapsed >= idle_seconds:
            log.info(
                f"#{channel} ({channel.id}) is idle longer than {idle_seconds} seconds "
                f"and will be made dormant."
            )

            await self.move_to_dormant(channel, "auto")
        else:
            # Cancel the existing task, if any.
            if has_task:
                self.scheduler.cancel(channel.id)

            delay = idle_seconds - time_elapsed
            log.info(
                f"#{channel} ({channel.id}) is still active; "
                f"scheduling it to be moved after {delay} seconds."
            )

            self.scheduler.schedule_later(delay, channel.id, self.move_idle_channel(channel))

    async def move_to_bottom_position(self, channel: discord.TextChannel, category_id: int, **options) -> None:
        """
        Move the `channel` to the bottom position of `category` and edit channel attributes.

        To ensure "stable sorting", we use the `bulk_channel_update` endpoint and provide the current
        positions of the other channels in the category as-is. This should make sure that the channel
        really ends up at the bottom of the category.

        If `options` are provided, the channel will be edited after the move is completed. This is the
        same order of operations that `discord.TextChannel.edit` uses. For information on available
        options, see the documentation on `discord.TextChannel.edit`. While possible, position-related
        options should be avoided, as it may interfere with the category move we perform.
        """
        # Get a fresh copy of the category from the bot to avoid the cache mismatch issue we had.
        category = await channel_utils.try_get_channel(category_id)

        payload = [{"id": c.id, "position": c.position} for c in category.channels]

        # Calculate the bottom position based on the current highest position in the category. If the
        # category is currently empty, we simply use the current position of the channel to avoid making
        # unnecessary changes to positions in the guild.
        bottom_position = payload[-1]["position"] + 1 if payload else channel.position

        payload.append(
            {
                "id": channel.id,
                "position": bottom_position,
                "parent_id": category.id,
                "lock_permissions": True,
            }
        )

        # We use d.py's method to ensure our request is processed by d.py's rate limit manager
        await self.bot.http.bulk_channel_update(category.guild.id, payload)

        # Now that the channel is moved, we can edit the other attributes
        if options:
            await channel.edit(**options)

    async def move_to_available(self) -> None:
        """Make a channel available."""
        log.trace("Making a channel available.")

        channel = await self.get_available_candidate()
        log.info(f"Making #{channel} ({channel.id}) available.")

        await _message.send_available_message(channel)

        log.trace(f"Moving #{channel} ({channel.id}) to the Available category.")

        await self.move_to_bottom_position(
            channel=channel,
            category_id=constants.Categories.help_available,
        )

        self.report_stats()

    async def move_to_dormant(self, channel: discord.TextChannel, caller: str) -> None:
        """
        Make the `channel` dormant.

        A caller argument is provided for metrics.
        """
        log.info(f"Moving #{channel} ({channel.id}) to the Dormant category.")

        await self.help_channel_claimants.delete(channel.id)
        await self.move_to_bottom_position(
            channel=channel,
            category_id=constants.Categories.help_dormant,
        )

        self.bot.stats.incr(f"help.dormant_calls.{caller}")

        in_use_time = await _channel.get_in_use_time(channel.id)
        if in_use_time:
            self.bot.stats.timing("help.in_use_time", in_use_time)

        unanswered = await _message.unanswered.get(channel.id)
        if unanswered:
            self.bot.stats.incr("help.sessions.unanswered")
        elif unanswered is not None:
            self.bot.stats.incr("help.sessions.answered")

        log.trace(f"Position of #{channel} ({channel.id}) is actually {channel.position}.")
        log.trace(f"Sending dormant message for #{channel} ({channel.id}).")
        embed = discord.Embed(description=_message.DORMANT_MSG)
        await channel.send(embed=embed)

        await _message.unpin(channel)

        log.trace(f"Pushing #{channel} ({channel.id}) into the channel queue.")
        self.channel_queue.put_nowait(channel)
        self.report_stats()

    async def move_to_in_use(self, channel: discord.TextChannel) -> None:
        """Make a channel in-use and schedule it to be made dormant."""
        log.info(f"Moving #{channel} ({channel.id}) to the In Use category.")

        await self.move_to_bottom_position(
            channel=channel,
            category_id=constants.Categories.help_in_use,
        )

        timeout = constants.HelpChannels.idle_minutes * 60

        log.trace(f"Scheduling #{channel} ({channel.id}) to become dormant in {timeout} sec.")
        self.scheduler.schedule_later(timeout, channel.id, self.move_idle_channel(channel))
        self.report_stats()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Move an available channel to the In Use category and replace it with a dormant one."""
        if message.author.bot:
            return  # Ignore messages sent by bots.

        channel = message.channel

        await _message.check_for_answer(message)

        is_available = channel_utils.is_in_category(channel, constants.Categories.help_available)
        if not is_available or _channel.is_excluded_channel(channel):
            return  # Ignore messages outside the Available category or in excluded channels.

        log.trace("Waiting for the cog to be ready before processing messages.")
        await self.ready.wait()

        log.trace("Acquiring lock to prevent a channel from being processed twice...")
        async with self.on_message_lock:
            log.trace(f"on_message lock acquired for {message.id}.")

            if not channel_utils.is_in_category(channel, constants.Categories.help_available):
                log.debug(
                    f"Message {message.id} will not make #{channel} ({channel.id}) in-use "
                    f"because another message in the channel already triggered that."
                )
                return

            log.info(f"Channel #{channel} was claimed by `{message.author.id}`.")
            await self.move_to_in_use(channel)
            await self.revoke_send_permissions(message.author)

            await _message.pin(message)

            # Add user with channel for dormant check.
            await self.help_channel_claimants.set(channel.id, message.author.id)

            self.bot.stats.incr("help.claimed")

            # Must use a timezone-aware datetime to ensure a correct POSIX timestamp.
            timestamp = datetime.now(timezone.utc).timestamp()
            await self.claim_times.set(channel.id, timestamp)

            await _message.unanswered.set(channel.id, True)

            log.trace(f"Releasing on_message lock for {message.id}.")

        # Move a dormant channel to the Available category to fill in the gap.
        # This is done last and outside the lock because it may wait indefinitely for a channel to
        # be put in the queue.
        await self.move_to_available()

    @commands.Cog.listener()
    async def on_message_delete(self, msg: discord.Message) -> None:
        """
        Reschedule an in-use channel to become dormant sooner if the channel is empty.

        The new time for the dormant task is configured with `HelpChannels.deleted_idle_minutes`.
        """
        if not channel_utils.is_in_category(msg.channel, constants.Categories.help_in_use):
            return

        if not await _message.is_empty(msg.channel):
            return

        log.info(f"Claimant of #{msg.channel} ({msg.author}) deleted message, channel is empty now. Rescheduling task.")

        # Cancel existing dormant task before scheduling new.
        self.scheduler.cancel(msg.channel.id)

        delay = constants.HelpChannels.deleted_idle_minutes * 60
        self.scheduler.schedule_later(delay, msg.channel.id, self.move_idle_channel(msg.channel))

    async def check_cooldowns(self) -> None:
        """Remove expired cooldowns and re-schedule active ones."""
        log.trace("Checking all cooldowns to remove or re-schedule them.")
        guild = self.bot.get_guild(constants.Guild.id)
        cooldown = constants.HelpChannels.claim_minutes * 60

        for channel_id, member_id in await self.help_channel_claimants.items():
            member = guild.get_member(member_id)
            if not member:
                continue  # Member probably left the guild.

            in_use_time = await self.get_in_use_time(channel_id)

            if not in_use_time or in_use_time.seconds > cooldown:
                # Remove the role if no claim time could be retrieved or if the cooldown expired.
                # Since the channel is in the claimants cache, it is definitely strange for a time
                # to not exist. However, it isn't a reason to keep the user stuck with a cooldown.
                await self.remove_cooldown_role(member)
            else:
                # The member is still on a cooldown; re-schedule it for the remaining time.
                delay = cooldown - in_use_time.seconds
                self.scheduler.schedule_later(delay, member.id, self.remove_cooldown_role(member))

    async def add_cooldown_role(self, member: discord.Member) -> None:
        """Add the help cooldown role to `member`."""
        log.trace(f"Adding cooldown role for {member} ({member.id}).")
        await self._change_cooldown_role(member, member.add_roles)

    async def remove_cooldown_role(self, member: discord.Member) -> None:
        """Remove the help cooldown role from `member`."""
        log.trace(f"Removing cooldown role for {member} ({member.id}).")
        await self._change_cooldown_role(member, member.remove_roles)

    async def _change_cooldown_role(self, member: discord.Member, coro_func: CoroutineFunc) -> None:
        """
        Change `member`'s cooldown role via awaiting `coro_func` and handle errors.

        `coro_func` is intended to be `discord.Member.add_roles` or `discord.Member.remove_roles`.
        """
        guild = self.bot.get_guild(constants.Guild.id)
        role = guild.get_role(constants.Roles.help_cooldown)
        if role is None:
            log.warning(f"Help cooldown role ({constants.Roles.help_cooldown}) could not be found!")
            return

        try:
            await coro_func(role)
        except discord.NotFound:
            log.debug(f"Failed to change role for {member} ({member.id}): member not found")
        except discord.Forbidden:
            log.debug(
                f"Forbidden to change role for {member} ({member.id}); "
                f"possibly due to role hierarchy"
            )
        except discord.HTTPException as e:
            log.error(f"Failed to change role for {member} ({member.id}): {e.status} {e.code}")

    async def revoke_send_permissions(self, member: discord.Member) -> None:
        """
        Disallow `member` to send messages in the Available category for a certain time.

        The time until permissions are reinstated can be configured with
        `HelpChannels.claim_minutes`.
        """
        log.trace(
            f"Revoking {member}'s ({member.id}) send message permissions in the Available category."
        )

        await self.add_cooldown_role(member)

        # Cancel the existing task, if any.
        # Would mean the user somehow bypassed the lack of permissions (e.g. user is guild owner).
        if member.id in self.scheduler:
            self.scheduler.cancel(member.id)

        delay = constants.HelpChannels.claim_minutes * 60
        self.scheduler.schedule_later(delay, member.id, self.remove_cooldown_role(member))

    async def wait_for_dormant_channel(self) -> discord.TextChannel:
        """Wait for a dormant channel to become available in the queue and return it."""
        log.trace("Waiting for a dormant channel.")

        task = asyncio.create_task(self.channel_queue.get())
        self.queue_tasks.append(task)
        channel = await task

        log.trace(f"Channel #{channel} ({channel.id}) finally retrieved from the queue.")
        self.queue_tasks.remove(task)

        return channel
