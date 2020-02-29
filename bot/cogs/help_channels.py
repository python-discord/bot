import asyncio
import itertools
import json
import logging
import random
import typing as t
from collections import deque
from datetime import datetime
from pathlib import Path

import discord
from discord.ext import commands

from bot import constants
from bot.bot import Bot
from bot.decorators import with_role
from bot.utils.scheduling import Scheduler

log = logging.getLogger(__name__)

# TODO: write the channel topics
AVAILABLE_TOPIC = ""
IN_USE_TOPIC = ""
DORMANT_TOPIC = ""
ASKING_GUIDE_URL = "https://pythondiscord.com/pages/asking-good-questions/"
MAX_CHANNELS_PER_CATEGORY = 50

AVAILABLE_MSG = f"""
This help channel is now **available**, which means that you can claim it by simply typing your \
question into it. Once claimed, the channel will move into the **Help: In Use** category, and will \
be yours until it has been inactive for {constants.HelpChannels.idle_minutes} minutes. When that \
happens, it will be set to **dormant** and moved into the **Help: Dormant** category.

Try to write the best question you can by providing a detailed description and telling us what \
you've tried already. For more information on asking a good question, \
[check out our guide on asking good questions]({ASKING_GUIDE_URL}).
"""

DORMANT_MSG = f"""
This help channel has been marked as **dormant**, and has been moved into the **Help: Dormant** \
category at the bottom of the channel list. It is no longer possible to send messages in this \
channel until it becomes available again.

If your question wasn't answered yet, you can claim a new help channel from the \
**Help: Available** category by simply asking your question again. Consider rephrasing the \
question to maximize your chance of getting a good answer. If you're not sure how, have a look \
through [our guide for asking a good question]({ASKING_GUIDE_URL}).
"""


class ChannelTimeout(t.NamedTuple):
    """Data for a task scheduled to make a channel dormant."""

    channel: discord.TextChannel
    timeout: int


class HelpChannels(Scheduler, commands.Cog):
    """
    Manage the help channel system of the guild.

    The system is based on a 3-category system:

    Available Category

    * Contains channels which are ready to be occupied by someone who needs help
    * Will always contain 2 channels; refilled automatically from the pool of dormant channels
        * Prioritise using the channels which have been dormant for the longest amount of time
        * If there are no more dormant channels, the bot will automatically create a new one
        * Configurable with `constants.HelpChannels.max_available`
    * When a channel becomes available, the dormant embed will be edited to show `AVAILABLE_MSG`

    In Use Category

    * Contains all channels which are occupied by someone needing help
    * Channel moves to dormant category after 45 minutes of being idle
        * Configurable with `constants.HelpChannels.idle_minutes`
    * Helpers+ command can prematurely mark a channel as dormant
        * Configurable with `constants.HelpChannels.cmd_whitelist`
    * When a channel becomes dormant, an embed with `DORMANT_MSG` will be sent

    Dormant Category

    * Contains channels which aren't in use
    * Channels are used to refill the Available category

    Help channels are named after the chemical elements in `bot/resources/elements.json`.
    """

    def __init__(self, bot: Bot):
        super().__init__()

        self.bot = bot

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

    def cog_unload(self) -> None:
        """Cancel the init task and scheduled tasks when the cog unloads."""
        log.trace("Cog unload: cancelling the cog_init task")
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

    @commands.command(name="dormant")
    @with_role(*constants.HelpChannels.cmd_whitelist)
    async def dormant_command(self, ctx: commands.Context) -> None:
        """Make the current in-use help channel dormant."""
        log.trace("dormant command invoked; checking if the channel is in-use.")

        in_use = self.get_category_channels(self.in_use_category)
        if ctx.channel in in_use:
            self.cancel_task(ctx.channel.id)
            await self.move_to_dormant(ctx.channel)
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

    def get_alphabetical_position(self, channel: discord.TextChannel) -> t.Optional[int]:
        """
        Return the position to move `channel` to so alphabetic order is maintained.

        If the channel does not have a valid name with a chemical element, return None.
        """
        log.trace(f"Getting alphabetical position for #{channel.name} ({channel.id}).")

        try:
            position = self.name_positions[channel.name]
        except KeyError:
            log.warning(f"Channel #{channel.name} ({channel.id}) doesn't have a valid name.")
            position = None

        log.trace(
            f"Position of #{channel.name} ({channel.id}) in Dormant will be {position} "
            f"(was {channel.position})."
        )

        return position

    @staticmethod
    def get_category_channels(category: discord.CategoryChannel) -> t.Iterable[discord.TextChannel]:
        """Yield the text channels of the `category` in an unsorted manner."""
        log.trace(f"Getting text channels in the category '{category.name}' ({category.id}).")

        # This is faster than using category.channels because the latter sorts them.
        for channel in category.guild.channels:
            if channel.category_id == category.id and isinstance(channel, discord.TextChannel):
                yield channel

    @staticmethod
    def get_names() -> t.Dict[str, int]:
        """
        Return a truncated dict of prefixed element names and their alphabetical indices.

        The amount of names if configured with `HelpChannels.max_total_channels`.
        The prefix is configured with `HelpChannels.name_prefix`.
        """
        count = constants.HelpChannels.max_total_channels
        prefix = constants.HelpChannels.name_prefix

        log.trace(f"Getting the first {count} element names from JSON.")

        if count > MAX_CHANNELS_PER_CATEGORY:
            log.warning(
                f"{count} is too many help channels to make available! "
                f"Discord only supports at most {MAX_CHANNELS_PER_CATEGORY} channels per category."
            )

        with Path("bot/resources/elements.json").open(encoding="utf-8") as elements_file:
            all_names = json.load(elements_file)

        names = itertools.islice(all_names.items(), count)
        if prefix:
            names = ((prefix + name, pos) for name, pos in names)

        return dict(names)

    def get_used_names(self) -> t.Set[str]:
        """Return channels names which are already being used."""
        log.trace("Getting channel names which are already being used.")

        names = set()
        for cat in (self.available_category, self.in_use_category, self.dormant_category):
            for channel in self.get_category_channels(cat):
                names.add(channel.name)

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
        log.trace(f"Getting the idle time for #{channel.name} ({channel.id}).")

        msg = await cls.get_last_message(channel)
        if not msg:
            log.debug(f"No idle time available; #{channel.name} ({channel.id}) has no messages.")
            return None

        idle_time = (datetime.utcnow() - msg.created_at).seconds

        log.trace(f"#{channel.name} ({channel.id}) has been idle for {idle_time} seconds.")
        return idle_time

    @staticmethod
    async def get_last_message(channel: discord.TextChannel) -> t.Optional[discord.Message]:
        """Return the last message sent in the channel or None if no messages exist."""
        log.trace(f"Getting the last message in #{channel.name} ({channel.id}).")

        try:
            return await channel.history(limit=1).next()  # noqa: B305
        except discord.NoMoreItems:
            log.debug(f"No last message available; #{channel.name} ({channel.id}) has no messages.")
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

        self.channel_queue = self.create_channel_queue()
        self.name_queue = self.create_name_queue()

        await self.init_available()

        log.trace("Moving or rescheduling in-use channels.")
        for channel in self.get_category_channels(self.in_use_category):
            await self.move_idle_channel(channel, has_task=False)

        log.info("Cog is ready!")
        self.ready.set()

    @staticmethod
    def is_dormant_message(message: t.Optional[discord.Message]) -> bool:
        """Return True if the contents of the `message` match `DORMANT_MSG`."""
        if not message or not message.embeds:
            return False

        embed = message.embeds[0]
        return embed.description.strip() == DORMANT_MSG.strip()

    async def move_idle_channel(self, channel: discord.TextChannel, has_task: bool = True) -> None:
        """
        Make the `channel` dormant if idle or schedule the move if still active.

        If `has_task` is True and rescheduling is required, the extant task to make the channel
        dormant will first be cancelled.
        """
        log.trace(f"Handling in-use channel #{channel.name} ({channel.id}).")

        idle_seconds = constants.HelpChannels.idle_minutes * 60
        time_elapsed = await self.get_idle_time(channel)

        if time_elapsed is None or time_elapsed >= idle_seconds:
            log.info(
                f"#{channel.name} ({channel.id}) is idle longer than {idle_seconds} seconds "
                f"and will be made dormant."
            )

            await self.move_to_dormant(channel)
        else:
            # Cancel the existing task, if any.
            if has_task:
                self.cancel_task(channel.id)

            data = ChannelTimeout(channel, idle_seconds - time_elapsed)

            log.info(
                f"#{channel.name} ({channel.id}) is still active; "
                f"scheduling it to be moved after {data.timeout} seconds."
            )

            self.schedule_task(channel.id, data)

    async def move_to_available(self) -> None:
        """Make a channel available."""
        log.trace("Making a channel available.")

        channel = await self.get_available_candidate()
        log.info(f"Making #{channel.name} ({channel.id}) available.")

        await self.send_available_message(channel)

        log.trace(f"Moving #{channel.name} ({channel.id}) to the Available category.")
        await channel.edit(
            category=self.available_category,
            sync_permissions=True,
            topic=AVAILABLE_TOPIC,
        )

    async def move_to_dormant(self, channel: discord.TextChannel) -> None:
        """Make the `channel` dormant."""
        log.info(f"Moving #{channel.name} ({channel.id}) to the Dormant category.")

        await channel.edit(
            category=self.dormant_category,
            sync_permissions=True,
            topic=DORMANT_TOPIC,
            position=self.get_alphabetical_position(channel),
        )

        log.trace(f"Position of #{channel.name} ({channel.id}) is actually {channel.position}.")

        log.trace(f"Sending dormant message for #{channel.name} ({channel.id}).")
        embed = discord.Embed(description=DORMANT_MSG)
        await channel.send(embed=embed)

        log.trace(f"Pushing #{channel.name} ({channel.id}) into the channel queue.")
        self.channel_queue.put_nowait(channel)

    async def move_to_in_use(self, channel: discord.TextChannel) -> None:
        """Make a channel in-use and schedule it to be made dormant."""
        log.info(f"Moving #{channel.name} ({channel.id}) to the In Use category.")

        await channel.edit(
            category=self.in_use_category,
            sync_permissions=True,
            topic=IN_USE_TOPIC,
            position=0,
        )

        timeout = constants.HelpChannels.idle_minutes * 60

        log.trace(f"Scheduling #{channel.name} ({channel.id}) to become dormant in {timeout} sec.")
        data = ChannelTimeout(channel, timeout)
        self.schedule_task(channel.id, data)

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

            await channel.send(
                f"{mentions} A new available help channel is needed but there "
                f"are no more dormant ones. Consider freeing up some in-use channels manually by "
                f"using the `!dormant` command within the channels."
            )
        except Exception:
            # Handle it here cause this feature isn't critical for the functionality of the system.
            log.exception("Failed to send notification about lack of dormant channels!")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Move an available channel to the In Use category and replace it with a dormant one."""
        if message.author.bot:
            return  # Ignore messages sent by bots.

        log.trace("Waiting for the cog to be ready before processing messages.")
        await self.ready.wait()

        log.trace("Acquiring lock to prevent a channel from being processed twice...")
        async with self.on_message_lock:
            log.trace("on_message lock acquired.")
            log.trace("Checking if the message was sent in an available channel.")

            available_channels = self.get_category_channels(self.available_category)
            if message.channel not in available_channels:
                return  # Ignore messages outside the Available category.

            await self.move_to_in_use(message.channel)
            log.trace("Releasing on_message lock.")

        # Move a dormant channel to the Available category to fill in the gap.
        # This is done last and outside the lock because it may wait indefinitely for a channel to
        # be put in the queue.
        await self.move_to_available()

    async def send_available_message(self, channel: discord.TextChannel) -> None:
        """Send the available message by editing a dormant message or sending a new message."""
        channel_info = f"#{channel.name} ({channel.id})"
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

        log.trace(f"Channel #{channel.name} ({channel_id}) retrieved.")
        return channel

    async def wait_for_dormant_channel(self) -> discord.TextChannel:
        """Wait for a dormant channel to become available in the queue and return it."""
        log.trace("Waiting for a dormant channel.")

        task = asyncio.create_task(self.channel_queue.get())
        self.queue_tasks.append(task)
        channel = await task

        log.trace(f"Channel #{channel.name} ({channel.id}) finally retrieved from the queue.")
        self.queue_tasks.remove(task)

        return channel

    async def _scheduled_task(self, data: ChannelTimeout) -> None:
        """Make a channel dormant after specified timeout or reschedule if it's still active."""
        log.trace(f"Waiting {data.timeout} seconds before making #{data.channel.name} dormant.")
        await asyncio.sleep(data.timeout)

        # Use asyncio.shield to prevent move_idle_channel from cancelling itself.
        # The parent task (_scheduled_task) will still get cancelled.
        await asyncio.shield(self.move_idle_channel(data.channel))


def setup(bot: Bot) -> None:
    """Load the HelpChannels cog."""
    bot.add_cog(HelpChannels(bot))
