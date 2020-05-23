import unittest
from unittest.mock import patch

from bot.cogs.jams import CodeJams
from bot.constants import Roles
from tests.helpers import MockBot, MockContext, MockMember, MockRole


class JamCreateTeamTests(unittest.IsolatedAsyncioTestCase):
    """Tests for `createteam` command."""

    def setUp(self):
        self.bot = MockBot()
        self.admin_role = MockRole(name="Admins", id=Roles.admins)
        self.command_user = MockMember([self.admin_role])
        self.ctx = MockContext(bot=self.bot, author=self.command_user)
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
