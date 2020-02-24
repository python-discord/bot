import asyncio
import json
import logging
import random
import typing as t
from collections import deque
from pathlib import Path

import discord
from discord.ext import commands

from bot import constants
from bot.bot import Bot
from bot.utils.scheduling import Scheduler

log = logging.getLogger(__name__)

ASKING_GUIDE_URL = "https://pythondiscord.com/pages/asking-good-questions/"

AVAILABLE_MSG = f"""
This help channel is now **available**, which means that you can claim it by simply typing your \
question into it. Once claimed, the channel will move into the **Help: In Use** category, and will \
be yours until it has been inactive for {constants.HelpChannels.idle_minutes}. When that happens, \
it will be set to **dormant** and moved into the **Help: Dormant** category.

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

with Path("bot/resources/elements.json").open(encoding="utf-8") as elements_file:
    ELEMENTS = json.load(elements_file)


class ChannelTimeout(t.NamedTuple):
    """Data for a task scheduled to make a channel dormant."""

    channel: discord.TextChannel
    timeout: int


class HelpChannels(Scheduler, commands.Cog):
    """Manage the help channel system of the guild."""

    def __init__(self, bot: Bot):
        super().__init__()

        self.bot = bot

        self.available_category: discord.CategoryChannel = None
        self.in_use_category: discord.CategoryChannel = None
        self.dormant_category: discord.CategoryChannel = None

        self.channel_queue: asyncio.Queue = None
        self.name_queue: deque = None

        self.ready = asyncio.Event()
        self.init_task = asyncio.create_task(self.init_cog())

    async def cog_unload(self) -> None:
        """Cancel the init task if the cog unloads."""
        self.init_task.cancel()

    def create_channel_queue(self) -> asyncio.Queue:
        """
        Return a queue of dormant channels to use for getting the next available channel.

        The channels are added to the queue in a random order.
        """
        channels = list(self.get_category_channels(self.dormant_category))
        random.shuffle(channels)

        queue = asyncio.Queue()
        for channel in channels:
            queue.put_nowait(channel)

        return queue

    async def create_dormant(self) -> discord.TextChannel:
        """Create and return a new channel in the Dormant category."""

    def create_name_queue(self) -> deque:
        """Return a queue of element names to use for creating new channels."""
        used_names = self.get_used_names()
        available_names = (name for name in ELEMENTS if name not in used_names)

        return deque(available_names)

    @commands.command(name="dormant")
    async def dormant_command(self) -> None:
        """Make the current in-use help channel dormant."""

    async def get_available_candidate(self) -> discord.TextChannel:
        """Return a dormant channel to turn into an available channel."""

    @staticmethod
    def get_category_channels(category: discord.CategoryChannel) -> t.Iterable[discord.TextChannel]:
        """Yield the text channels of the `category` in an unsorted manner."""
        # This is faster than using category.channels because the latter sorts them.
        for channel in category.guild.channels:
            if channel.category_id == category.id and isinstance(channel, discord.TextChannel):
                yield channel

    def get_used_names(self) -> t.Set[str]:
        """Return channels names which are already being used."""
        start_index = len(constants.HelpChannels.name_prefix)

        names = set()
        for cat in (self.available_category, self.in_use_category, self.dormant_category):
            for channel in self.get_category_channels(cat):
                name = channel.name[start_index:]
                names.add(name)

        return names

    async def get_idle_time(self, channel: discord.TextChannel) -> int:
        """Return the time elapsed since the last message sent in the `channel`."""

    async def init_available(self) -> None:
        """Initialise the Available category with channels."""
        channels = list(self.get_category_channels(self.available_category))
        missing = constants.HelpChannels.max_available - len(channels)

        for _ in range(missing):
            await self.move_to_available()

    async def init_categories(self) -> None:
        """Get the help category objects. Remove the cog if retrieval fails."""
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
        await self.bot.wait_until_guild_available()

        await self.init_categories()

        self.channel_queue = self.create_channel_queue()
        self.name_queue = self.create_name_queue()

        await self.init_available()
        await self.move_idle_channels()

        self.ready.set()

    async def move_idle_channels(self) -> None:
        """Make all in-use channels dormant if idle or schedule the move if still active."""
        idle_seconds = constants.HelpChannels.idle_minutes * 60

        for channel in self.get_category_channels(self.in_use_category):
            time_elapsed = await self.get_idle_time(channel)
            if time_elapsed > idle_seconds:
                await self.move_to_dormant(channel)
            else:
                data = ChannelTimeout(channel, idle_seconds - time_elapsed)
                self.schedule_task(self.bot.loop, channel.id, data)

    async def move_to_available(self) -> None:
        """Make a channel available."""

    async def move_to_dormant(self, channel: discord.TextChannel) -> None:
        """Make the `channel` dormant."""

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Move an available channel to the In Use category and replace it with a dormant one."""

    async def try_get_channel(self, channel_id: int) -> discord.abc.GuildChannel:
        """Attempt to get or fetch a channel and return it."""
        channel = self.bot.get_channel(channel_id)
        if not channel:
            channel = await self.bot.fetch_channel(channel_id)

        return channel

    async def _scheduled_task(self, data: ChannelTimeout) -> None:
        """Make a channel dormant after specified timeout or reschedule if it's still active."""


def setup(bot: Bot) -> None:
    """Load the HelpChannels cog."""
    bot.add_cog(HelpChannels(bot))
