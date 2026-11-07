import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bot.bot import Bot, BotContext
from bot.exts.info.help import HelpFormatter


class BotContextSendHelpTests(unittest.IsolatedAsyncioTestCase):
    """Tests for `BotContext.send_help`."""

    def setUp(self):
        self.bot = MagicMock()
        self.bot.get_cog.return_value = MagicMock(formatter=HelpFormatter())
        self.ctx = BotContext.__new__(BotContext)
        self.ctx.bot = self.bot
        self.ctx.command = MagicMock(qualified_name="filter")

    async def test_defaults_to_invoked_command(self):
        """Help for the invoked command is sent when no entity is given."""
        with patch.object(HelpFormatter, "send_help_for", new_callable=AsyncMock) as send_help_for:
            await self.ctx.send_help()

        send_help_for.assert_awaited_once_with("filter")

    async def test_explicit_entity(self):
        """Help for the given command is sent."""
        with patch.object(HelpFormatter, "send_help_for", new_callable=AsyncMock) as send_help_for:
            await self.ctx.send_help(MagicMock(qualified_name="filter list"))

        send_help_for.assert_awaited_once_with("filter list")

    async def test_no_help_cog_is_a_noop(self):
        """Nothing happens, and nothing raises, when the help cog isn't loaded."""
        self.bot.get_cog.return_value = None
        await self.ctx.send_help()


class ExtensionLoadingTests(unittest.IsolatedAsyncioTestCase):
    """Tests that syncing waits until every extension has finished loading."""

    def setUp(self):
        self.bot = Bot.__new__(Bot)
        self.bot.all_extensions = frozenset({"a", "b"})
        self.bot._finished_extensions = set()
        self.bot._extensions_finished_loading = asyncio.Event()

    async def test_event_set_only_after_all_extensions_finish(self):
        """The event is set once every extension has finished, including failed loads."""
        with patch("bot.bot.BotBase.load_extension", new_callable=AsyncMock) as load:
            await self.bot.load_extension("a")
            self.assertFalse(self.bot._extensions_finished_loading.is_set())

            load.side_effect = RuntimeError
            with self.assertRaises(RuntimeError):
                await self.bot.load_extension("b")

        self.assertTrue(self.bot._extensions_finished_loading.is_set())
