import collections
import unittest
import unittest.mock

from bot.decorators import InWhitelistedContextCheckFailure, in_whitelisted_context
from tests import helpers


WhitelistedContextTestCase = collections.namedtuple("WhitelistedContextTestCase", ("kwargs", "ctx"))


class InWhitelistedContextTests(unittest.TestCase):
    """Tests for the `in_whitelisted_context` check."""

    @classmethod
    def setUpClass(cls):
        """Set up helpers that only need to be defined once."""
        cls.bot_commands = helpers.MockTextChannel(id=123456789, category_id=123456)
        cls.help_channel = helpers.MockTextChannel(id=987654321, category_id=987654)
        cls.non_whitelisted_channel = helpers.MockTextChannel(id=666666)

        cls.non_staff_member = helpers.MockMember()
        cls.staff_role = helpers.MockRole(id=121212)
        cls.staff_member = helpers.MockMember(roles=(cls.staff_role,))

        cls.whitelisted_channels = (cls.bot_commands.id,)
        cls.whitelisted_categories = (cls.help_channel.category_id,)
        cls.whitelisted_roles = (cls.staff_role.id,)

    def test_predicate_returns_true_for_whitelisted_context(self):
        """The predicate should return `True` if a whitelisted context was passed to it."""
        test_cases = (
            # Commands issued in whitelisted channels by members without whitelisted roles
            WhitelistedContextTestCase(
                kwargs={"whitelisted_channels": self.whitelisted_channels},
                ctx=helpers.MockContext(channel=self.bot_commands, author=self.non_staff_member)
            ),
            # `redirect_channel` should be added implicitly to the `whitelisted_channels`
            WhitelistedContextTestCase(
                kwargs={"redirect_channel": self.bot_commands.id},
                ctx=helpers.MockContext(channel=self.bot_commands, author=self.non_staff_member)
            ),

            # Commands issued in a whitelisted category by members without whitelisted roles
            WhitelistedContextTestCase(
                kwargs={"whitelisted_categories": self.whitelisted_categories},
                ctx=helpers.MockContext(channel=self.help_channel, author=self.non_staff_member)
            ),

            # Command issued by a staff member in a non-whitelisted channel/category
            WhitelistedContextTestCase(
                kwargs={"whitelisted_roles": self.whitelisted_roles},
                ctx=helpers.MockContext(channel=self.non_whitelisted_channel, author=self.staff_member)
            ),

            # With all kwargs provided
            WhitelistedContextTestCase(
                kwargs={
                    "whitelisted_channels": self.whitelisted_channels,
                    "whitelisted_categories": self.whitelisted_categories,
                    "whitelisted_roles": self.whitelisted_roles,
                    "redirect_channel": self.bot_commands,
                },
                ctx=helpers.MockContext(channel=self.help_channel, author=self.staff_member)
            ),
        )

        for test_case in test_cases:
            # patch `commands.check` with a no-op lambda that just returns the predicate passed to it
            # so we can test the predicate that was generated from the specified kwargs.
            with unittest.mock.patch("bot.decorators.commands.check", new=lambda predicate: predicate):
                predicate = in_whitelisted_context(**test_case.kwargs)

            with self.subTest(test_case=test_case):
                self.assertTrue(predicate(test_case.ctx))

    def test_predicate_raises_exception_for_non_whitelisted_context(self):
        """The predicate should raise `InWhitelistedContextCheckFailure` for a non-whitelisted context."""
        test_cases = (
            # Failing check with `redirect_channel`
            WhitelistedContextTestCase(
                kwargs={
                    "whitelisted_categories": self.whitelisted_categories,
                    "whitelisted_channels": self.whitelisted_channels,
                    "whitelisted_roles": self.whitelisted_roles,
                    "redirect_channel": self.bot_commands.id,
                },
                ctx=helpers.MockContext(channel=self.non_whitelisted_channel, author=self.non_staff_member)
            ),

            # Failing check without `redirect_channel`
            WhitelistedContextTestCase(
                kwargs={
                    "whitelisted_categories": self.whitelisted_categories,
                    "whitelisted_channels": self.whitelisted_channels,
                    "whitelisted_roles": self.whitelisted_roles,
                },
                ctx=helpers.MockContext(channel=self.non_whitelisted_channel, author=self.non_staff_member)
            ),
        )

        for test_case in test_cases:
            # Create expected exception message based on whether or not a redirect channel was provided
            expected_message = "Sorry, but you are not allowed to use that command here."
            if test_case.kwargs.get("redirect_channel"):
                expected_message += f" Please use the <#{test_case.kwargs['redirect_channel']}> channel instead."

            # patch `commands.check` with a no-op lambda that just returns the predicate passed to it
            # so we can test the predicate that was generated from the specified kwargs.
            with unittest.mock.patch("bot.decorators.commands.check", new=lambda predicate: predicate):
                predicate = in_whitelisted_context(**test_case.kwargs)

            with self.subTest(test_case=test_case):
                with self.assertRaises(InWhitelistedContextCheckFailure, msg=expected_message):
                    predicate(test_case.ctx)
