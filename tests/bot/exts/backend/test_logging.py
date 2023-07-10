import unittest
from unittest.mock import patch

from bot import constants
from bot.exts.backend.logging import Logging
from tests.helpers import MockBot, MockTextChannel, no_create_task


class LoggingTests(unittest.IsolatedAsyncioTestCase):
    """Test cases for connected login."""

    def setUp(self):
        self.bot = MockBot()
        with no_create_task():
            self.cog = Logging(self.bot)
        self.dev_log = MockTextChannel(id=1234, name="dev-log")

    @patch("bot.exts.backend.logging.DEBUG_MODE", False)
    async def test_debug_mode_false(self):
        """Should send connected message to dev-log."""
        self.bot.get_channel.return_value = self.dev_log

        await self.cog.startup_greeting()
        self.bot.wait_until_guild_available.assert_awaited_once_with()
        self.bot.get_channel.assert_called_once_with(constants.Channels.dev_log)
        self.dev_log.send.assert_awaited_once()

    @patch("bot.exts.backend.logging.DEBUG_MODE", True)
    async def test_debug_mode_true(self):
        """Should not send anything to dev-log."""
        await self.cog.startup_greeting()
        self.bot.wait_until_guild_available.assert_awaited_once_with()
        self.bot.get_channel.assert_not_called()
