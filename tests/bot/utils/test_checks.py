import unittest

from bot.utils import checks
from tests.helpers import MockContext, MockRole


class ChecksTests(unittest.TestCase):
    """Tests the check functions defined in `bot.checks`."""

    def setUp(self):
        self.ctx = MockContext()

    def test_with_role_check_without_guild(self):
        """`with_role_check` returns `False` if `Context.guild` is None."""
        self.ctx.guild = None
        self.assertFalse(checks.with_role_check(self.ctx))

    def test_with_role_check_without_required_roles(self):
        """`with_role_check` returns `False` if `Context.author` lacks the required role."""
        self.ctx.author.roles = []
        self.assertFalse(checks.with_role_check(self.ctx))

    def test_with_role_check_with_guild_and_required_role(self):
        """`with_role_check` returns `True` if `Context.author` has the required role."""
        self.ctx.author.roles.append(MockRole(id=10))
        self.assertTrue(checks.with_role_check(self.ctx, 10))

    def test_without_role_check_without_guild(self):
        """`without_role_check` should return `False` when `Context.guild` is None."""
        self.ctx.guild = None
        self.assertFalse(checks.without_role_check(self.ctx))

    def test_without_role_check_returns_false_with_unwanted_role(self):
        """`without_role_check` returns `False` if `Context.author` has unwanted role."""
        role_id = 42
        self.ctx.author.roles.append(MockRole(id=role_id))
        self.assertFalse(checks.without_role_check(self.ctx, role_id))

    def test_without_role_check_returns_true_without_unwanted_role(self):
        """`without_role_check` returns `True` if `Context.author` does not have unwanted role."""
        role_id = 42
        self.ctx.author.roles.append(MockRole(id=role_id))
        self.assertTrue(checks.without_role_check(self.ctx, role_id + 10))

    def test_in_channel_check_for_correct_channel(self):
        self.ctx.channel.id = 42
        self.assertTrue(checks.in_channel_check(self.ctx, *[42]))

    def test_in_channel_check_for_incorrect_channel(self):
        self.ctx.channel.id = 42 + 10
        self.assertFalse(checks.in_channel_check(self.ctx, *[42]))
