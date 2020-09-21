import unittest

import discord

from bot.exts.moderation.modlog import ModLog
from tests.helpers import MockBot, MockTextChannel


class ModLogTests(unittest.IsolatedAsyncioTestCase):
    """Tests for moderation logs."""

    def setUp(self):
        self.bot = MockBot()
        self.cog = ModLog(self.bot)
        self.channel = MockTextChannel()

    async def test_log_entry_description_truncation(self):
        """Test that embed description for ModLog entry is truncated."""
        self.bot.get_channel.return_value = self.channel
        await self.cog.send_log_message(
            icon_url="foo",
            colour=discord.Colour.blue(),
            title="bar",
            text="foo bar" * 3000
        )
        embed = self.channel.send.call_args[1]["embed"]
        self.assertEqual(
            embed.description, ("foo bar" * 3000)[:2045] + "..."
        )
