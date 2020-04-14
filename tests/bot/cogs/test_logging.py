import unittest
from unittest.mock import patch

from bot import constants
from bot.cogs.logging import Logging
from tests.helpers import MockBot, MockTextChannel


class LoggingTests(unittest.IsolatedAsyncioTestCase):
    """Test cases for connected login."""

    def setUp(self):
        self.bot = MockBot()
        self.cog = Logging(self.bot)
        self.dev_log = MockTextChannel(id=1234, name="dev-log")

    @patch("bot.cogs.logging.DEBUG_MODE", False)
    async def test_debug_mode_false(self):
        """Should send connected message to dev-log."""
        self.bot.get_channel.return_value = self.dev_log

        await self.cog.startup_greeting()
        self.bot.wait_until_guild_available.assert_awaited_once_with()
        self.bot.get_channel.assert_called_once_with(constants.Channels.dev_log)

        embed = self.dev_log.send.call_args[1]['embed']
        self.dev_log.send.assert_awaited_once_with(embed=embed)

        self.assertEqual(embed.description, "Connected!")
        self.assertEqual(embed.author.name, "Python Bot")
        self.assertEqual(embed.author.url, "https://github.com/python-discord/bot")
        self.assertEqual(
            embed.author.icon_url,
            "https://raw.githubusercontent.com/python-discord/branding/master/logos/logo_circle/logo_circle_large.png"
        )

    @patch("bot.cogs.logging.DEBUG_MODE", True)
    async def test_debug_mode_true(self):
        """Should not send anything to dev-log."""
        await self.cog.startup_greeting()
        self.bot.wait_until_guild_available.assert_awaited_once_with()
        self.bot.get_channel.assert_not_called()
