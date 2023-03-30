import unittest

from discord.ext.commands import NoPrivateMessage

from bot.exts.backend import security
from tests.helpers import MockBot, MockContext


class SecurityCogTests(unittest.TestCase):
    """Tests the `Security` cog."""

    def setUp(self):
        """Attach an instance of the cog to the class for tests."""
        self.bot = MockBot()
        self.cog = security.Security(self.bot)
        self.ctx = MockContext()

    def test_check_additions(self):
        """The cog should add its checks after initialization."""
        self.bot.check.assert_any_call(self.cog.check_on_guild)
        self.bot.check.assert_any_call(self.cog.check_not_bot)

    def test_check_not_bot_returns_false_for_humans(self):
        """The bot check should return `True` when invoked with human authors."""
        self.ctx.author.bot = False
        self.assertTrue(self.cog.check_not_bot(self.ctx))

    def test_check_not_bot_returns_true_for_robots(self):
        """The bot check should return `False` when invoked with robotic authors."""
        self.ctx.author.bot = True
        self.assertFalse(self.cog.check_not_bot(self.ctx))

    def test_check_on_guild_raises_when_outside_of_guild(self):
        """When invoked outside of a guild, `check_on_guild` should cause an error."""
        self.ctx.guild = None

        with self.assertRaises(NoPrivateMessage, msg="This command cannot be used in private messages."):
            self.cog.check_on_guild(self.ctx)

    def test_check_on_guild_returns_true_inside_of_guild(self):
        """When invoked inside of a guild, `check_on_guild` should return `True`."""
        self.ctx.guild = "lemon's lemonade stand"
        self.assertTrue(self.cog.check_on_guild(self.ctx))


class SecurityCogLoadTests(unittest.IsolatedAsyncioTestCase):
    """Tests loading the `Security` cog."""

    async def test_security_cog_load(self):
        """Setup of the extension should call add_cog."""
        bot = MockBot()
        await security.setup(bot)
        bot.add_cog.assert_awaited_once()
