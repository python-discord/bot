import asyncio
import json
import logging
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


class HelpChannels(Scheduler, commands.Cog):
    """Manage the help channel system of the guild."""

    def __init__(self, bot: Bot):
        super().__init__()

        self.bot = bot

    async def create_channel_queue(self) -> asyncio.Queue:
        """Return a queue of dormant channels to use for getting the next available channel."""

    async def create_dormant(self) -> discord.TextChannel:
        """Create and return a new channel in the Dormant category."""

    async def create_name_queue(self) -> deque:
        """Return a queue of element names to use for creating new channels."""

    @commands.command(name="dormant")
    async def dormant_command(self) -> None:
        """Make the current in-use help channel dormant."""

    async def get_available_candidate(self) -> discord.TextChannel:
        """Return a dormant channel to turn into an available channel."""

    async def get_idle_time(self, channel: discord.TextChannel) -> int:
        """Return the time elapsed since the last message sent in the `channel`."""

    async def init_available(self) -> None:
        """Initialise the Available category with channels."""

    async def move_idle_channels(self) -> None:
        """Make all idle in-use channels dormant."""

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

    async def _scheduled_task(self, channel: discord.TextChannel, timeout: int) -> None:
        """Make the `channel` dormant after `timeout` seconds or reschedule if it's still active."""


def setup(bot: Bot) -> None:
    """Load the HelpChannels cog."""
    bot.add_cog(HelpChannels(bot))
