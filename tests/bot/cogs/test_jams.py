import unittest

from bot.constants import Roles
from tests.helpers import MockBot, MockContext, MockMember, MockRole


class JamCreateTeamTests(unittest.IsolatedAsyncioTestCase):
    """Tests for `createteam` command."""

    def setUp(self):
        self.bot = MockBot()
        self.admin_role = MockRole(name="Admins", id=Roles.admins)
        self.command_user = MockMember([self.admin_role])
        self.context = MockContext(bot=self.bot, author=self.command_user)
