import unittest
from unittest.mock import patch

from bot.cogs.jams import CodeJams
from bot.constants import Roles
from tests.helpers import MockBot, MockContext, MockGuild, MockMember, MockRole


class JamCreateTeamTests(unittest.IsolatedAsyncioTestCase):
    """Tests for `createteam` command."""

    def setUp(self):
        self.bot = MockBot()
        self.admin_role = MockRole(name="Admins", id=Roles.admins)
        self.command_user = MockMember([self.admin_role])
        self.guild = MockGuild([self.admin_role])
        self.ctx = MockContext(bot=self.bot, author=self.command_user, guild=self.guild)
        self.cog = CodeJams(self.bot)

    @patch("bot.cogs.jams.utils")
    async def test_too_small_amount_of_team_members_passed(self, utils_mock):
        """Should `ctx.send` and exit early when too small amount of members."""
        for case in (1, 2):
            with self.subTest(amount_of_members=case):
                self.ctx.reset_mock()
                utils_mock.reset_mock()
                await self.cog.createteam(
                    self.cog, self.ctx, team_name="foo", members=(MockMember() for _ in range(case))
                )
                self.ctx.send.assert_awaited_once()
                utils_mock.get.assert_not_called()

    @patch("bot.cogs.jams.utils")
    async def test_duplicate_members_provided(self, utils_mock):
        """Should `ctx.send` and exit early because duplicate members provided and total there is only 1 member."""
        self.ctx.reset_mock()
        member = MockMember()
        await self.cog.createteam(self.cog, self.ctx, "foo", (member for _ in range(5)))
        self.ctx.send.assert_awaited_once()
        utils_mock.get.assert_not_called()

    @patch("bot.cogs.jams.utils")
    async def test_category_dont_exist(self, utils_mock):
        """Should create code jam category."""
        utils_mock.get.return_value = None
        await self.cog.createteam(self.cog, self.ctx, "foo", (MockMember() for _ in range(5)))
        utils_mock.get.assert_called_once()
        self.ctx.guild.create_category_channel.assert_awaited_once()
        category_overwrites = self.ctx.guild.create_category_channel.call_args[1]["overwrites"]

        self.assertFalse(category_overwrites[self.ctx.guild.default_role].read_messages)
        self.assertTrue(category_overwrites[self.ctx.guild.me].read_messages)

    @patch("bot.cogs.jams.utils")
    async def test_category_channel_exist(self, utils_mock):
        """Should not try to create category channel."""
        utils_mock.return_value = "foo"
        await self.cog.createteam(self.cog, self.ctx, "bar", (MockMember() for _ in range(5)))
        utils_mock.get.assert_called_once()
        self.ctx.guild.create_category_channel.assert_not_awaited()

    async def test_team_text_channel_creation(self):
        """Should create text channel for team."""
        await self.cog.createteam(self.cog, self.ctx, "bar", (MockMember() for _ in range(5)))
        self.ctx.guild.create_text_channel.assert_awaited_once()
