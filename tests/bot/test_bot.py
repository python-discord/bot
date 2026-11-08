import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bot import constants
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


class DeprecatedPrefixTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the notice sent when the old prefix is used."""

    def setUp(self):
        from discord.ext import commands

        from bot.utils.hybrid import hybrid_command, hybrid_group

        class TestCog(commands.Cog):
            @hybrid_group(fallback="get")
            async def things(self, ctx): ...

            @things.command(name="search")
            async def search(self, ctx): ...

            @commands.command()
            async def plain(self, ctx): ...

            @hybrid_command()
            async def solo(self, ctx): ...

        self.bot = Bot.__new__(Bot)
        self.commands = {
            "things": TestCog.things,
            "solo": TestCog.solo,
            "plain": TestCog.plain,
        }
        self.bot.get_command = lambda name: self.commands.get(name)
        self.message = MagicMock(content="", author=MagicMock(bot=False))

        prefix_patcher = patch.object(constants.Bot, "prefix", "!")
        prefix_patcher.start()
        self.addCleanup(prefix_patcher.stop)

    def notice(self, content: str) -> str | None:
        self.message.content = content
        command = self.bot._get_deprecated_prefix_command(self.message)
        if command is None:
            return None
        with patch.object(Bot, "user", MagicMock(display_name="Python"), create=True):
            return self.bot._build_deprecated_prefix_notice(command)

    def test_slash_and_mention_forms(self):
        self.assertEqual(
            self.notice("!solo"),
            "Using the `!` prefix is deprecated due to restrictions placed on us by Discord, "
            "please use `@Python solo` or the slash command `/solo` to use this bot.",
        )

    def test_group_callback_uses_fallback_and_subcommands_are_resolved(self):
        self.assertIn("`/things get`", self.notice("!things 5"))
        self.assertIn("`@Python things search` or the slash command `/things search`", self.notice("!things search x"))

    def test_prefix_only_command_has_no_slash_form(self):
        notice = self.notice("!plain")
        self.assertIn("`@Python plain`", notice)
        self.assertNotIn("slash", notice)

    def test_unknown_commands_and_bots_are_ignored(self):
        self.assertIsNone(self.notice("!nope"))
        self.assertIsNone(self.notice("hello"))
        self.message.author.bot = True
        self.assertIsNone(self.notice("!solo"))


class WhitespaceAfterPrefixTests(unittest.TestCase):
    """Tests for finding the command when extra whitespace follows the mention."""

    def setUp(self):
        self.bot = Bot.__new__(Bot)
        self.ping = object()
        self.bot.__dict__["all_commands"] = {"ping": self.ping}
        self.prefix = "<@1> "

    def _ctx(self, content: str):
        message = MagicMock(content=content)
        ctx = MagicMock(command=None, prefix=self.prefix)
        self.bot._skip_whitespace_after_prefix(ctx, message)
        return ctx

    def test_extra_spaces_are_ignored(self):
        for spaces in (" ", "   ", " \t"):
            with self.subTest(spaces=repr(spaces)):
                ctx = self._ctx(f"<@1> {spaces}ping arg")

                self.assertIs(ctx.command, self.ping)
                self.assertEqual(ctx.invoked_with, "ping")
                self.assertEqual(ctx.view.buffer[ctx.view.index:], " arg")

    def test_unknown_command_is_still_unknown(self):
        ctx = self._ctx("<@1>  nope")

        self.assertIsNone(ctx.command)
        self.assertEqual(ctx.invoked_with, "nope")

    def test_found_commands_are_untouched(self):
        found = object()
        ctx = MagicMock(command=found, prefix=self.prefix)

        self.bot._skip_whitespace_after_prefix(ctx, MagicMock(content="<@1> ping"))

        self.assertIs(ctx.command, found)
