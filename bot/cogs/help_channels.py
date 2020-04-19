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
from discord.ext import commands

from bot import constants
from bot.bot import Bot
from bot.utils.checks import with_role_check
from bot.utils.scheduling import Scheduler

log = logging.getLogger(__name__)

ASKING_GUIDE_URL = "https://pythondiscord.com/pages/asking-good-questions/"
MAX_CHANNELS_PER_CATEGORY = 50

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
and will be yours until it has been inactive for {constants.HelpChannels.idle_minutes} minutes. When \
that happens, it will be set to **dormant** and moved into the **Help: Dormant** category.

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
IN_USE_EMOJI = "⌛"
NAME_SEPARATOR = "｜"


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

    In Use Category

    * Contains all channels which are occupied by someone needing help
    * Channel moves to dormant category after `constants.HelpChannels.idle_minutes` of being idle
    * Command can prematurely mark a channel as dormant
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
        self.claim_times = {}

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

    @commands.command(name="dormant", aliases=["close"], enabled=False)
    async def dormant_command(self, ctx: commands.Context) -> None:
        """
        Make the current in-use help channel dormant.

        Make the channel dormant if the user passes the `dormant_check`,
        delete the message that invoked this,
        and reset the send permissions cooldown for the user who started the session.
        """
        log.trace("dormant command invoked; checking if the channel is in-use.")
        if ctx.channel.category == self.in_use_category:
            if await self.dormant_check(ctx):
                with suppress(KeyError):
                    del self.help_channel_claimants[ctx.channel]

                with suppress(discord.errors.HTTPException, discord.errors.NotFound):
                    await self.reset_claimant_send_permission(ctx.channel)

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
            log.info(f"Can't get clean name as `{channel}` does not follow the `{prefix}` naming convention.")
            name = channel.name

        return name

    @staticmethod
    def get_category_channels(category: discord.CategoryChannel) -> t.Iterable[discord.TextChannel]:
        """Yield the text channels of the `category` in an unsorted manner."""
        log.trace(f"Getting text channels in the category '{category}' ({category.id}).")

        # This is faster than using category.channels because the latter sorts them.
        for channel in category.guild.channels:
            if channel.category_id == category.id and isinstance(channel, discord.TextChannel):
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
        self.dormant_command.enabled = True

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

    def is_dormant_message(self, message: t.Optional[discord.Message]) -> bool:
        """Return True if the contents of the `message` match `DORMANT_MSG`."""
        if not message or not message.embeds:
            return False

        embed = message.embeds[0]
        return message.author == self.bot.user and embed.description.strip() == DORMANT_MSG.strip()

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

        idle_seconds = constants.HelpChannels.idle_minutes * 60
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

    async def move_to_available(self) -> None:
        """Make a channel available."""
        log.trace("Making a channel available.")

        channel = await self.get_available_candidate()
        log.info(f"Making #{channel} ({channel.id}) available.")

        await self.send_available_message(channel)

        log.trace(f"Moving #{channel} ({channel.id}) to the Available category.")

        await channel.edit(
            name=f"{AVAILABLE_EMOJI}{NAME_SEPARATOR}{self.get_clean_channel_name(channel)}",
            category=self.available_category,
            sync_permissions=True,
            topic=AVAILABLE_TOPIC,
        )

        log.trace(
            f"Ensuring that all channels in `{self.available_category}` have "
            f"synchronized permissions after moving `{channel}` into it."
        )
        await self.ensure_permissions_synchronization(self.available_category)
        self.report_stats()

    async def move_to_dormant(self, channel: discord.TextChannel, caller: str) -> None:
        """
        Make the `channel` dormant.

        A caller argument is provided for metrics.
        """
        log.info(f"Moving #{channel} ({channel.id}) to the Dormant category.")

        await channel.edit(
            name=self.get_clean_channel_name(channel),
            category=self.dormant_category,
            sync_permissions=True,
            topic=DORMANT_TOPIC,
        )

        self.bot.stats.incr(f"help.dormant_calls.{caller}")

        if channel.id in self.claim_times:
            claimed = self.claim_times[channel.id]
            in_use_time = datetime.now() - claimed
            self.bot.stats.timing("help.in_use_time", in_use_time)

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

        await channel.edit(
            name=f"{IN_USE_EMOJI}{NAME_SEPARATOR}{self.get_clean_channel_name(channel)}",
            category=self.in_use_category,
            sync_permissions=True,
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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Move an available channel to the In Use category and replace it with a dormant one."""
        if message.author.bot:
            return  # Ignore messages sent by bots.

        channel = message.channel
        if not self.is_in_category(channel, constants.Categories.help_available):
            return  # Ignore messages outside the Available category.

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

            await self.move_to_in_use(channel)
            await self.revoke_send_permissions(message.author)
            # Add user with channel for dormant check.
            self.help_channel_claimants[channel] = message.author

            self.bot.stats.incr("help.claimed")

            self.claim_times[channel.id] = datetime.now()

            log.trace(f"Releasing on_message lock for {message.id}.")

        # Move a dormant channel to the Available category to fill in the gap.
        # This is done last and outside the lock because it may wait indefinitely for a channel to
        # be put in the queue.
        await self.move_to_available()

    @staticmethod
    async def ensure_permissions_synchronization(category: discord.CategoryChannel) -> None:
        """
        Ensure that all channels in the `category` have their permissions synchronized.

        This method mitigates an issue we have yet to find the cause for: Every so often, a channel in the
        `Help: Available` category gets in a state in which it will no longer synchronizes its permissions
        with the category. To prevent that, we iterate over the channels in the category and edit the channels
        that are observed to be in such a state. If no "out of sync" channels are observed, this method will
        not make API calls and should be fairly inexpensive to run.
        """
        for channel in category.channels:
            if not channel.permissions_synced:
                log.info(f"The permissions of channel `{channel}` were out of sync with category `{category}`.")
                await channel.edit(sync_permissions=True)

    async def update_category_permissions(
        self, category: discord.CategoryChannel, member: discord.Member, **permissions
    ) -> None:
        """
        Update the permissions of the given `member` for the given `category` with `permissions` passed.

        After updating the permissions for the member in the category, this helper function will call the
        `ensure_permissions_synchronization` method to ensure that all channels are still synchronizing their
        permissions with the category. It's currently unknown why some channels get "out of sync", but this
        hopefully mitigates the issue.
        """
        log.trace(f"Updating permissions for `{member}` in `{category}` with {permissions}.")
        await category.set_permissions(member, **permissions)

        log.trace(f"Ensuring that all channels in `{category}` are synchronized after permissions update.")
        await self.ensure_permissions_synchronization(category)

    async def reset_send_permissions(self) -> None:
        """Reset send permissions for members with it set to False in the Available category."""
        log.trace("Resetting send permissions in the Available category.")

        for member, overwrite in self.available_category.overwrites.items():
            if isinstance(member, discord.Member) and overwrite.send_messages is False:
                log.trace(f"Resetting send permissions for {member} ({member.id}).")

                # We don't use the permissions helper function here as we may have to reset multiple overwrites
                # and we don't want to enforce the permissions synchronization in each iteration.
                await self.available_category.set_permissions(member, overwrite=None)

        log.trace(f"Ensuring channels in `Help: Available` are synchronized after permissions reset.")
        await self.ensure_permissions_synchronization(self.available_category)

    async def reset_claimant_send_permission(self, channel: discord.TextChannel) -> None:
        """Reset send permissions in the Available category for the help `channel` claimant."""
        log.trace(f"Attempting to find claimant for #{channel.name} ({channel.id}).")
        try:
            member = self.help_channel_claimants[channel]
        except KeyError:
            log.trace(f"Channel #{channel.name} ({channel.id}) not in claimant cache, permissions unchanged.")
            return

        log.trace(f"Resetting send permissions for {member} ({member.id}).")
        await self.update_category_permissions(self.available_category, member, overwrite=None)
        # Ignore missing task when claim cooldown has passed but the channel still isn't dormant.
        self.cancel_task(member.id, ignore_missing=True)

    async def revoke_send_permissions(self, member: discord.Member) -> None:
        """
        Disallow `member` to send messages in the Available category for a certain time.

        The time until permissions are reinstated can be configured with
        `HelpChannels.claim_minutes`.
        """
        log.trace(
            f"Revoking {member}'s ({member.id}) send message permissions in the Available category."
        )

        await self.update_category_permissions(self.available_category, member, send_messages=False)

        # Cancel the existing task, if any.
        # Would mean the user somehow bypassed the lack of permissions (e.g. user is guild owner).
        self.cancel_task(member.id, ignore_missing=True)

        timeout = constants.HelpChannels.claim_minutes * 60
        callback = self.update_category_permissions(self.available_category, member, overwrite=None)

        log.trace(f"Scheduling {member}'s ({member.id}) send message permissions to be reinstated.")
        self.schedule_task(member.id, TaskData(timeout, callback))

    async def send_available_message(self, channel: discord.TextChannel) -> None:
        """Send the available message by editing a dormant message or sending a new message."""
        channel_info = f"#{channel} ({channel.id})"
        log.trace(f"Sending available message in {channel_info}.")

        embed = discord.Embed(description=AVAILABLE_MSG)

        msg = await self.get_last_message(channel)
        if self.is_dormant_message(msg):
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
