import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import rapidfuzz
from discord.ext import commands

from bot.exts.info import help
from bot.utils.hybrid import hybrid_command
from tests.helpers import MockBot, MockContext, autospec


class HelpCogTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        """Attach an instance of the cog to the class for tests."""
        self.bot = MockBot()
        self.cog = help.Help(self.bot)
        self.ctx = MockContext(bot=self.bot)
        self.formatter = help.HelpFormatter(self.ctx)

    def test_help_replaces_default_help_command(self):
        """The discord.py help command should be disabled by the cog and restored on unload."""
        self.assertIsNone(self.bot.help_command)

    @autospec(help.HelpFormatter, "get_all_help_choices", return_value={"help"}, pass_mocks=False)
    async def test_help_fuzzy_matching(self):
        """Test fuzzy matching of commands when called from help."""
        result = await self.formatter.command_not_found("holp")

        match = {"help": rapidfuzz.fuzz.ratio("help", "holp")}
        self.assertEqual(match, result.possible_matches)

    async def test_help_callback_sends_help_for_query(self):
        """The command should hand the query to the formatter."""
        with patch.object(help.HelpFormatter, "send_help_for", new=AsyncMock()) as send_help_for:
            await self.cog.help_command.callback.__wrapped__(self.cog, self.ctx, query="remind")

        send_help_for.assert_awaited_once_with("remind")
        self.assertIs(self.cog.formatter.context, self.ctx)


class HelpFormatterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.bot = MockBot()
        self.ctx = MockContext(bot=self.bot)
        self.ctx.me.display_name = "Python"
        self.formatter = help.HelpFormatter(self.ctx)

    @staticmethod
    def make_command(name: str, **kwargs) -> commands.Command:
        async def callback(ctx, arg: str = "x") -> None: ...

        return hybrid_command(name, **kwargs)(callback)

    def test_usage_for_slash_and_prefix_only_commands(self):
        """Hybrid commands are shown as slash commands, everything else with a mention."""
        slash = self.make_command("thing")
        prefix_only = self.make_command("other", with_app_command=False)

        async def plain_callback(ctx) -> None: ...

        plain = commands.Command(plain_callback, name="eval")

        self.assertEqual("/thing [arg=x]", self.formatter.get_usage(slash))
        self.assertEqual("@Python other [arg=x]", self.formatter.get_usage(prefix_only))
        self.assertEqual("@Python eval", self.formatter.get_usage(plain))

    def test_usage_for_group_with_fallback(self):
        """A group with a fallback is used as `/group fallback`."""
        async def callback(ctx) -> None: ...

        group = help.HybridGroup(callback, name="grp", fallback="get")
        self.assertEqual("/grp get", self.formatter.get_usage(group))

    def test_resolve(self):
        """Queries resolve to categories first, then cogs, then commands."""
        categorised = MagicMock(category="Cat", category_description="desc")
        cog = MagicMock()
        self.bot.cogs = {"Categorised": categorised, "Other": cog}
        command = self.make_command("thing")
        self.bot.get_cog.side_effect = lambda name: cog if name == "Other" else None
        self.bot.get_command.side_effect = lambda name: command if name == "thing" else None

        category = self.formatter.resolve("Cat")
        self.assertEqual(help.Category("Cat", "desc", [categorised]), category)
        self.assertIs(cog, self.formatter.resolve("Other"))
        self.assertIs(command, self.formatter.resolve("/thing"))
        self.assertIsNone(self.formatter.resolve("missing"))

    async def test_filter_commands(self):
        """Hidden commands and commands the invoker can't run are removed, the rest are sorted."""
        allowed_b, allowed_a = self.make_command("b"), self.make_command("a")
        hidden = self.make_command("c", hidden=True)
        denied = self.make_command("d")
        for cmd in (allowed_a, allowed_b, hidden, denied):
            cmd.can_run = AsyncMock(return_value=cmd is not denied)
        denied.can_run.side_effect = commands.CheckFailure

        result = await self.formatter.filter_commands([allowed_b, hidden, denied, allowed_a], sort=True)

        self.assertEqual([allowed_a, allowed_b], result)

    async def test_send_help_for_missing_query(self):
        """An unknown query sends the not found error."""
        self.bot.cogs = {}
        self.bot.get_cog.return_value = None
        self.bot.get_command.return_value = None
        error = help.HelpQueryNotFoundError("nope")
        self.formatter.command_not_found = AsyncMock(return_value=error)
        self.formatter.send_error_message = AsyncMock()

        await self.formatter.send_help_for("missing")

        self.formatter.send_error_message.assert_awaited_once_with(error)


class AutocompleteTests(unittest.TestCase):
    def test_empty_text_returns_sorted_limited_choices(self):
        choices = [f"cmd{i:02}" for i in range(40)]
        result = help.get_autocomplete_choices(choices, "")
        self.assertEqual(sorted(choices)[:25], result)

    def test_filters_on_typed_text_with_prefix_matches_first(self):
        result = help.get_autocomplete_choices(["tag list", "list", "remind list", "unrelated"], "/list")
        self.assertEqual(["list", "tag list", "remind list"], result[:3])
        self.assertNotIn("unrelated", result)

    def test_fuzzy_fallback_for_typos(self):
        result = help.get_autocomplete_choices(["remind", "tag"], "remnd")
        self.assertEqual(["remind"], result)

    def test_never_more_than_25(self):
        result = help.get_autocomplete_choices([f"tag {i}" for i in range(100)], "tag")
        self.assertEqual(25, len(result))
