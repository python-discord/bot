import asyncio
import inspect
import json
import logging
import random
import typing as t
from collections import deque
from contextlib import suppress
from datetime import datetime
from pathlib import Path

import discord
import discord.abc
from discord.ext import commands

from bot import constants
from bot.bot import Bot
from bot.utils.checks import with_role_check
from bot.utils.scheduling import Scheduler

log = logging.getLogger(__name__)

ASKING_GUIDE_URL = "https://pythondiscord.com/pages/asking-good-questions/"
MAX_CHANNELS_PER_CATEGORY = 50
EXCLUDED_CHANNELS = (constants.Channels.how_to_get_help,)

AVAILABLE_TOPIC = """
This channel is available. Feel free to ask a question in order to claim this channel!
"""

IN_USE_TOPIC = """
This channel is currently in use. If you'd like to discuss a different problem, please claim a new \
channel from the Help: Available category.
"""

DORMANT_TOPIC = """
This channel is temporarily archived. If you'd like to ask a question, please use one of the \
channels in the Help: Available category.
"""

AVAILABLE_MSG = f"""
This help channel is now **available**, which means that you can claim it by simply typing your \
question into it. Once claimed, the channel will move into the **Python Help: Occupied** category, \
and will be yours until it has been inactive for {constants.HelpChannels.idle_minutes} minutes or \
is closed manually with `!close`. When that happens, it will be set to **dormant** and moved into \
the **Help: Dormant** category.

You may claim a new channel once every {constants.HelpChannels.claim_minutes} minutes. If you \
currently cannot send a message in this channel, it means you are on cooldown and need to wait.

Try to write the best question you can by providing a detailed description and telling us what \
you've tried already. For more information on asking a good question, \
check out our guide on [asking good questions]({ASKING_GUIDE_URL}).
"""

DORMANT_MSG = f"""
This help channel has been marked as **dormant**, and has been moved into the **Help: Dormant** \
category at the bottom of the channel list. It is no longer possible to send messages in this \
channel until it becomes available again.

If your question wasn't answered yet, you can claim a new help channel from the \
**Help: Available** category by simply asking your question again. Consider rephrasing the \
question to maximize your chance of getting a good answer. If you're not sure how, have a look \
through our guide for [asking a good question]({ASKING_GUIDE_URL}).
"""

AVAILABLE_EMOJI = "✅"
IN_USE_ANSWERED_EMOJI = "⌛"
IN_USE_UNANSWERED_EMOJI = "⏳"
NAME_SEPARATOR = "｜"

CoroutineFunc = t.Callable[..., t.Coroutine]


class TaskData(t.NamedTuple):
    """Data for a scheduled task."""

    wait_time: int
    callback: t.Awaitable


class HelpChannels(Scheduler, commands.Cog):
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

    def __init__(self, bot: Bot):
        super().__init__()

        self.bot = bot
        self.help_channel_claimants: (
            t.Dict[discord.TextChannel, t.Union[discord.Member, discord.User]]
        ) = {}

        # Categories
        self.available_category: discord.CategoryChannel = None
        self.in_use_category: discord.CategoryChannel = None
        self.dormant_category: discord.CategoryChannel = None

        # Queues
        self.channel_queue: asyncio.Queue[discord.TextChannel] = None
        self.name_queue: t.Deque[str] = None

        self.name_positions = self.get_names()
        self.last_notification: t.Optional[datetime] = None

        # Asyncio stuff
        self.queue_tasks: t.List[asyncio.Task] = []
        self.ready = asyncio.Event()
        self.on_message_lock = asyncio.Lock()
        self.init_task = self.bot.loop.create_task(self.init_cog())

        # Stats

        # This dictionary maps a help channel to the time it was claimed
        self.claim_times: t.Dict[int, datetime] = {}

        # This dictionary maps a help channel to whether it has had any
        # activity other than the original claimant. True being no other
        # activity and False being other activity.
        self.unanswered: t.Dict[int, bool] = {}

    def cog_unload(self) -> None:
        """Cancel the init task and scheduled tasks when the cog unloads."""
        log.trace("Cog unload: cancelling the init_cog task")
        self.init_task.cancel()

        log.trace("Cog unload: cancelling the channel queue tasks")
        for task in self.queue_tasks:
            task.cancel()

        self.cancel_all()

    def create_channel_queue(self) -> asyncio.Queue:
        """
        Return a queue of dormant channels to use for getting the next available channel.

        The channels are added to the queue in a random order.
        """
        log.trace("Creating the channel queue.")

        channels = list(self.get_category_channels(self.dormant_category))
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
        return await self.dormant_category.create_text_channel(name)

    def create_name_queue(self) -> deque:
        """Return a queue of element names to use for creating new channels."""
        log.trace("Creating the chemical element name queue.")

        used_names = self.get_used_names()

        log.trace("Determining the available names.")
        available_names = (name for name in self.name_positions if name not in used_names)

        log.trace("Populating the name queue with names.")
        return deque(available_names)

    async def dormant_check(self, ctx: commands.Context) -> bool:
        """Return True if the user is the help channel claimant or passes the role check."""
        if self.help_channel_claimants.get(ctx.channel) == ctx.author:
            log.trace(f"{ctx.author} is the help channel claimant, passing the check for dormant.")
            self.bot.stats.incr("help.dormant_invoke.claimant")
            return True

        log.trace(f"{ctx.author} is not the help channel claimant, checking roles.")
        role_check = with_role_check(ctx, *constants.HelpChannels.cmd_whitelist)

        if role_check:
            self.bot.stats.incr("help.dormant_invoke.staff")

        return role_check

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
                with suppress(KeyError):
                    del self.help_channel_claimants[ctx.channel]

                await self.remove_cooldown_role(ctx.author)
                # Ignore missing task when cooldown has passed but the channel still isn't dormant.
                self.cancel_task(ctx.author.id, ignore_missing=True)

                await self.move_to_dormant(ctx.channel, "command")
                self.cancel_task(ctx.channel.id)
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
                await self.notify()
                channel = await self.wait_for_dormant_channel()

        return channel

    @staticmethod
    def get_clean_channel_name(channel: discord.TextChannel) -> str:
        """Return a clean channel name without status emojis prefix."""
        prefix = constants.HelpChannels.name_prefix
        try:
            # Try to remove the status prefix using the index of the channel prefix
            name = channel.name[channel.name.index(prefix):]
            log.trace(f"The clean name for `{channel}` is `{name}`")
        except ValueError:
            # If, for some reason, the channel name does not contain "help-" fall back gracefully
            log.info(f"Can't get clean name because `{channel}` isn't prefixed by `{prefix}`.")
            name = channel.name

        return name

    @staticmethod
    def is_excluded_channel(channel: discord.abc.GuildChannel) -> bool:
        """Check if a channel should be excluded from the help channel system."""
        return not isinstance(channel, discord.TextChannel) or channel.id in EXCLUDED_CHANNELS

    def get_category_channels(self, category: discord.CategoryChannel) -> t.Iterable[discord.TextChannel]:
        """Yield the text channels of the `category` in an unsorted manner."""
        log.trace(f"Getting text channels in the category '{category}' ({category.id}).")

        # This is faster than using category.channels because the latter sorts them.
        for channel in self.bot.get_guild(constants.Guild.id).channels:
            if channel.category_id == category.id and not self.is_excluded_channel(channel):
                yield channel

    @staticmethod
    def get_names() -> t.List[str]:
        """
        Return a truncated list of prefixed element names.

        The amount of names is configured with `HelpChannels.max_total_channels`.
        The prefix is configured with `HelpChannels.name_prefix`.
        """
        count = constants.HelpChannels.max_total_channels
        prefix = constants.HelpChannels.name_prefix

        log.trace(f"Getting the first {count} element names from JSON.")

        with Path("bot/resources/elements.json").open(encoding="utf-8") as elements_file:
            all_names = json.load(elements_file)

        if prefix:
            return [prefix + name for name in all_names[:count]]
        else:
            return all_names[:count]

    def get_used_names(self) -> t.Set[str]:
        """Return channel names which are already being used."""
        log.trace("Getting channel names which are already being used.")

        names = set()
        for cat in (self.available_category, self.in_use_category, self.dormant_category):
            for channel in self.get_category_channels(cat):
                names.add(self.get_clean_channel_name(channel))

        if len(names) > MAX_CHANNELS_PER_CATEGORY:
            log.warning(
                f"Too many help channels ({len(names)}) already exist! "
                f"Discord only supports {MAX_CHANNELS_PER_CATEGORY} in a category."
            )

        log.trace(f"Got {len(names)} used names: {names}")
        return names

    @classmethod
    async def get_idle_time(cls, channel: discord.TextChannel) -> t.Optional[int]:
        """
        Return the time elapsed, in seconds, since the last message sent in the `channel`.

        Return None if the channel has no messages.
        """
        log.trace(f"Getting the idle time for #{channel} ({channel.id}).")

        msg = await cls.get_last_message(channel)
        if not msg:
            log.debug(f"No idle time available; #{channel} ({channel.id}) has no messages.")
            return None

        idle_time = (datetime.utcnow() - msg.created_at).seconds

        log.trace(f"#{channel} ({channel.id}) has been idle for {idle_time} seconds.")
        return idle_time

    @staticmethod
    async def get_last_message(channel: discord.TextChannel) -> t.Optional[discord.Message]:
        """Return the last message sent in the channel or None if no messages exist."""
        log.trace(f"Getting the last message in #{channel} ({channel.id}).")

        try:
            return await channel.history(limit=1).next()  # noqa: B305
        except discord.NoMoreItems:
            log.debug(f"No last message available; #{channel} ({channel.id}) has no messages.")
            return None

    async def init_available(self) -> None:
        """Initialise the Available category with channels."""
        log.trace("Initialising the Available category with channels.")

        channels = list(self.get_category_channels(self.available_category))
        missing = constants.HelpChannels.max_available - len(channels)

        log.trace(f"Moving {missing} missing channels to the Available category.")

        for _ in range(missing):
            await self.move_to_available()

    async def init_categories(self) -> None:
        """Get the help category objects. Remove the cog if retrieval fails."""
        log.trace("Getting the CategoryChannel objects for the help categories.")

        try:
            self.available_category = await self.try_get_channel(
                constants.Categories.help_available
            )
            self.in_use_category = await self.try_get_channel(constants.Categories.help_in_use)
            self.dormant_category = await self.try_get_channel(constants.Categories.help_dormant)
        except discord.HTTPException:
            log.exception(f"Failed to get a category; cog will be removed")
            self.bot.remove_cog(self.qualified_name)

    async def init_cog(self) -> None:
        """Initialise the help channel system."""
        log.trace("Waiting for the guild to be available before initialisation.")
        await self.bot.wait_until_guild_available()

        log.trace("Initialising the cog.")
        await self.init_categories()
        await self.reset_send_permissions()

        self.channel_queue = self.create_channel_queue()
        self.name_queue = self.create_name_queue()

        log.trace("Moving or rescheduling in-use channels.")
        for channel in self.get_category_channels(self.in_use_category):
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
        total_in_use = sum(1 for _ in self.get_category_channels(self.in_use_category))
        total_available = sum(1 for _ in self.get_category_channels(self.available_category))
        total_dormant = sum(1 for _ in self.get_category_channels(self.dormant_category))

        self.bot.stats.gauge("help.total.in_use", total_in_use)
        self.bot.stats.gauge("help.total.available", total_available)
        self.bot.stats.gauge("help.total.dormant", total_dormant)

    @staticmethod
    def is_claimant(member: discord.Member) -> bool:
        """Return True if `member` has the 'Help Cooldown' role."""
        return any(constants.Roles.help_cooldown == role.id for role in member.roles)

    def match_bot_embed(self, message: t.Optional[discord.Message], description: str) -> bool:
        """Return `True` if the bot's `message`'s embed description matches `description`."""
        if not message or not message.embeds:
            return False

        embed = message.embeds[0]
        return message.author == self.bot.user and embed.description.strip() == description.strip()

    @staticmethod
    def is_in_category(channel: discord.TextChannel, category_id: int) -> bool:
        """Return True if `channel` is within a category with `category_id`."""
        actual_category = getattr(channel, "category", None)
        return actual_category is not None and actual_category.id == category_id

    async def move_idle_channel(self, channel: discord.TextChannel, has_task: bool = True) -> None:
        """
        Make the `channel` dormant if idle or schedule the move if still active.

        If `has_task` is True and rescheduling is required, the extant task to make the channel
        dormant will first be cancelled.
        """
        log.trace(f"Handling in-use channel #{channel} ({channel.id}).")

        if not await self.is_empty(channel):
            idle_seconds = constants.HelpChannels.idle_minutes * 60
        else:
            idle_seconds = constants.HelpChannels.deleted_idle_minutes * 60

        time_elapsed = await self.get_idle_time(channel)

        if time_elapsed is None or time_elapsed >= idle_seconds:
            log.info(
                f"#{channel} ({channel.id}) is idle longer than {idle_seconds} seconds "
                f"and will be made dormant."
            )

            await self.move_to_dormant(channel, "auto")
        else:
            # Cancel the existing task, if any.
            if has_task:
                self.cancel_task(channel.id)

            data = TaskData(idle_seconds - time_elapsed, self.move_idle_channel(channel))

            log.info(
                f"#{channel} ({channel.id}) is still active; "
                f"scheduling it to be moved after {data.wait_time} seconds."
            )

            self.schedule_task(channel.id, data)

    async def move_to_bottom_position(self, channel: discord.TextChannel, category_id: int, **options) -> None:
        """
        Move the `channel` to the bottom position of `category` and edit channel attributes.

        To ensure "stable sorting", we use the `bulk_channel_update` endpoint and provide the current
        positions of the other channels in the category as-is. This should make sure that the channel
        really ends up at the bottom of the category.

        If `options` are provided, the channel will be edited after the move is completed. This is the
        same order of operations that `discord.TextChannel.edit` uses. For information on available
        options, see the documention on `discord.TextChannel.edit`. While possible, position-related
        options should be avoided, as it may interfere with the category move we perform.
        """
        # Get a fresh copy of the category from the bot to avoid the cache mismatch issue we had.
        category = await self.try_get_channel(category_id)

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

        await self.send_available_message(channel)

        log.trace(f"Moving #{channel} ({channel.id}) to the Available category.")

        await self.move_to_bottom_position(
            channel=channel,
            category_id=constants.Categories.help_available,
            name=f"{AVAILABLE_EMOJI}{NAME_SEPARATOR}{self.get_clean_channel_name(channel)}",
            topic=AVAILABLE_TOPIC,
        )

        self.report_stats()

    async def move_to_dormant(self, channel: discord.TextChannel, caller: str) -> None:
        """
        Make the `channel` dormant.

        A caller argument is provided for metrics.
        """
        log.info(f"Moving #{channel} ({channel.id}) to the Dormant category.")

        await self.move_to_bottom_position(
            channel=channel,
            category_id=constants.Categories.help_dormant,
            name=self.get_clean_channel_name(channel),
            topic=DORMANT_TOPIC,
        )

        self.bot.stats.incr(f"help.dormant_calls.{caller}")

        if channel.id in self.claim_times:
            claimed = self.claim_times[channel.id]
            in_use_time = datetime.now() - claimed
            self.bot.stats.timing("help.in_use_time", in_use_time)

        if channel.id in self.unanswered:
            if self.unanswered[channel.id]:
                self.bot.stats.incr("help.sessions.unanswered")
            else:
                self.bot.stats.incr("help.sessions.answered")

        log.trace(f"Position of #{channel} ({channel.id}) is actually {channel.position}.")

        log.trace(f"Sending dormant message for #{channel} ({channel.id}).")
        embed = discord.Embed(description=DORMANT_MSG)
        await channel.send(embed=embed)

        log.trace(f"Pushing #{channel} ({channel.id}) into the channel queue.")
        self.channel_queue.put_nowait(channel)
        self.report_stats()

    async def move_to_in_use(self, channel: discord.TextChannel) -> None:
        """Make a channel in-use and schedule it to be made dormant."""
        log.info(f"Moving #{channel} ({channel.id}) to the In Use category.")

        await self.move_to_bottom_position(
            channel=channel,
            category_id=constants.Categories.help_in_use,
            name=f"{IN_USE_UNANSWERED_EMOJI}{NAME_SEPARATOR}{self.get_clean_channel_name(channel)}",
            topic=IN_USE_TOPIC,
        )

        timeout = constants.HelpChannels.idle_minutes * 60

        log.trace(f"Scheduling #{channel} ({channel.id}) to become dormant in {timeout} sec.")
        data = TaskData(timeout, self.move_idle_channel(channel))
        self.schedule_task(channel.id, data)
        self.report_stats()

    async def notify(self) -> None:
        """
        Send a message notifying about a lack of available help channels.

        Configuration:

        * `HelpChannels.notify` - toggle notifications
        * `HelpChannels.notify_channel` - destination channel for notifications
        * `HelpChannels.notify_minutes` - minimum interval between notifications
        * `HelpChannels.notify_roles` - roles mentioned in notifications
        """
        if not constants.HelpChannels.notify:
            return

        log.trace("Notifying about lack of channels.")

        if self.last_notification:
            elapsed = (datetime.utcnow() - self.last_notification).seconds
            minimum_interval = constants.HelpChannels.notify_minutes * 60
            should_send = elapsed >= minimum_interval
        else:
            should_send = True

        if not should_send:
            log.trace("Notification not sent because it's too recent since the previous one.")
            return

        try:
            log.trace("Sending notification message.")

            channel = self.bot.get_channel(constants.HelpChannels.notify_channel)
            mentions = " ".join(f"<@&{role}>" for role in constants.HelpChannels.notify_roles)

            message = await channel.send(
                f"{mentions} A new available help channel is needed but there "
                f"are no more dormant ones. Consider freeing up some in-use channels manually by "
                f"using the `{constants.Bot.prefix}dormant` command within the channels."
            )

            self.bot.stats.incr("help.out_of_channel_alerts")

            self.last_notification = message.created_at
        except Exception:
            # Handle it here cause this feature isn't critical for the functionality of the system.
            log.exception("Failed to send notification about lack of dormant channels!")

    async def check_for_answer(self, message: discord.Message) -> None:
        """Checks for whether new content in a help channel comes from non-claimants."""
        channel = message.channel

        # Confirm the channel is an in use help channel
        if self.is_in_category(channel, constants.Categories.help_in_use):
            log.trace(f"Checking if #{channel} ({channel.id}) has been answered.")

            # Check if there is an entry in unanswered (does not persist across restarts)
            if channel.id in self.unanswered:
                claimant_id = self.help_channel_claimants[channel].id

                # Check the message did not come from the claimant
                if claimant_id != message.author.id:
                    # Mark the channel as answered
                    self.unanswered[channel.id] = False

                    # Change the emoji in the channel name to signify activity
                    log.trace(f"#{channel} ({channel.id}) has been answered; changing its emoji")
                    name = self.get_clean_channel_name(channel)
                    await channel.edit(name=f"{IN_USE_ANSWERED_EMOJI}{NAME_SEPARATOR}{name}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Move an available channel to the In Use category and replace it with a dormant one."""
        if message.author.bot:
            return  # Ignore messages sent by bots.

        channel = message.channel

        await self.check_for_answer(message)

        if not self.is_in_category(channel, constants.Categories.help_available) or self.is_excluded_channel(channel):
            return  # Ignore messages outside the Available category or in excluded channels.

        log.trace("Waiting for the cog to be ready before processing messages.")
        await self.ready.wait()

        log.trace("Acquiring lock to prevent a channel from being processed twice...")
        async with self.on_message_lock:
            log.trace(f"on_message lock acquired for {message.id}.")

            if not self.is_in_category(channel, constants.Categories.help_available):
                log.debug(
                    f"Message {message.id} will not make #{channel} ({channel.id}) in-use "
                    f"because another message in the channel already triggered that."
                )
                return

            log.info(f"Channel #{channel} was claimed by `{message.author.id}`.")
            await self.move_to_in_use(channel)
            await self.revoke_send_permissions(message.author)
            # Add user with channel for dormant check.
            self.help_channel_claimants[channel] = message.author

            self.bot.stats.incr("help.claimed")

            self.claim_times[channel.id] = datetime.now()
            self.unanswered[channel.id] = True

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
        if not self.is_in_category(msg.channel, constants.Categories.help_in_use):
            return

        if not await self.is_empty(msg.channel):
            return

        log.info(f"Claimant of #{msg.channel} ({msg.author}) deleted message, channel is empty now. Rescheduling task.")

        # Cancel existing dormant task before scheduling new.
        self.cancel_task(msg.channel.id)

        task = TaskData(constants.HelpChannels.deleted_idle_minutes * 60, self.move_idle_channel(msg.channel))
        self.schedule_task(msg.channel.id, task)

    async def is_empty(self, channel: discord.TextChannel) -> bool:
        """Return True if the most recent message in `channel` is the bot's `AVAILABLE_MSG`."""
        msg = await self.get_last_message(channel)
        return self.match_bot_embed(msg, AVAILABLE_MSG)

    async def reset_send_permissions(self) -> None:
        """Reset send permissions in the Available category for claimants."""
        log.trace("Resetting send permissions in the Available category.")
        guild = self.bot.get_guild(constants.Guild.id)

        # TODO: replace with a persistent cache cause checking every member is quite slow
        for member in guild.members:
            if self.is_claimant(member):
                await self.remove_cooldown_role(member)

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
        self.cancel_task(member.id, ignore_missing=True)

        timeout = constants.HelpChannels.claim_minutes * 60
        callback = self.remove_cooldown_role(member)

        log.trace(f"Scheduling {member}'s ({member.id}) send message permissions to be reinstated.")
        self.schedule_task(member.id, TaskData(timeout, callback))

    async def send_available_message(self, channel: discord.TextChannel) -> None:
        """Send the available message by editing a dormant message or sending a new message."""
        channel_info = f"#{channel} ({channel.id})"
        log.trace(f"Sending available message in {channel_info}.")

        embed = discord.Embed(description=AVAILABLE_MSG)

        msg = await self.get_last_message(channel)
        if self.match_bot_embed(msg, DORMANT_MSG):
            log.trace(f"Found dormant message {msg.id} in {channel_info}; editing it.")
            await msg.edit(embed=embed)
        else:
            log.trace(f"Dormant message not found in {channel_info}; sending a new message.")
            await channel.send(embed=embed)

    async def try_get_channel(self, channel_id: int) -> discord.abc.GuildChannel:
        """Attempt to get or fetch a channel and return it."""
        log.trace(f"Getting the channel {channel_id}.")

        channel = self.bot.get_channel(channel_id)
        if not channel:
            log.debug(f"Channel {channel_id} is not in cache; fetching from API.")
            channel = await self.bot.fetch_channel(channel_id)

        log.trace(f"Channel #{channel} ({channel_id}) retrieved.")
        return channel

    async def wait_for_dormant_channel(self) -> discord.TextChannel:
        """Wait for a dormant channel to become available in the queue and return it."""
        log.trace("Waiting for a dormant channel.")

        task = asyncio.create_task(self.channel_queue.get())
        self.queue_tasks.append(task)
        channel = await task

        log.trace(f"Channel #{channel} ({channel.id}) finally retrieved from the queue.")
        self.queue_tasks.remove(task)

        return channel

    async def _scheduled_task(self, data: TaskData) -> None:
        """Await the `data.callback` coroutine after waiting for `data.wait_time` seconds."""
        try:
            log.trace(f"Waiting {data.wait_time} seconds before awaiting callback.")
            await asyncio.sleep(data.wait_time)

            # Use asyncio.shield to prevent callback from cancelling itself.
            # The parent task (_scheduled_task) will still get cancelled.
            log.trace("Done waiting; now awaiting the callback.")
            await asyncio.shield(data.callback)
        finally:
            if inspect.iscoroutine(data.callback):
                log.trace("Explicitly closing coroutine.")
                data.callback.close()


def validate_config() -> None:
    """Raise a ValueError if the cog's config is invalid."""
    log.trace("Validating config.")
    total = constants.HelpChannels.max_total_channels
    available = constants.HelpChannels.max_available

    if total == 0 or available == 0:
        raise ValueError("max_total_channels and max_available and must be greater than 0.")

    if total < available:
        raise ValueError(
            f"max_total_channels ({total}) must be greater than or equal to max_available "
            f"({available})."
        )

    if total > MAX_CHANNELS_PER_CATEGORY:
        raise ValueError(
            f"max_total_channels ({total}) must be less than or equal to "
            f"{MAX_CHANNELS_PER_CATEGORY} due to Discord's limit on channels per category."
        )


def setup(bot: Bot) -> None:
    """Load the HelpChannels cog."""
    try:
        validate_config()
    except ValueError as e:
        log.error(f"HelpChannels cog will not be loaded due to misconfiguration: {e}")
    else:
        bot.add_cog(HelpChannels(bot))
