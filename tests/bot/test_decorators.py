import collections
import unittest
import unittest.mock

from bot.decorators import InWhitelistCheckFailure, in_whitelist
from tests import helpers


WhitelistedContextTestCase = collections.namedtuple("WhitelistedContextTestCase", ("kwargs", "ctx"))


class InWhitelistTests(unittest.TestCase):
    """Tests for the `in_whitelist` check."""

    @classmethod
    def setUpClass(cls):
        """Set up helpers that only need to be defined once."""
        cls.bot_commands = helpers.MockTextChannel(id=123456789, category_id=123456)
        cls.help_channel = helpers.MockTextChannel(id=987654321, category_id=987654)
        cls.non_whitelisted_channel = helpers.MockTextChannel(id=666666)

        cls.non_staff_member = helpers.MockMember()
        cls.staff_role = helpers.MockRole(id=121212)
        cls.staff_member = helpers.MockMember(roles=(cls.staff_role,))

        cls.channels = (cls.bot_commands.id,)
        cls.categories = (cls.help_channel.category_id,)
        cls.roles = (cls.staff_role.id,)

    def test_predicate_returns_true_for_whitelisted_context(self):
        """The predicate should return `True` if a whitelisted context was passed to it."""
        test_cases = (
            # Commands issued in whitelisted channels by members without whitelisted roles
            WhitelistedContextTestCase(
                kwargs={"channels": self.channels},
                ctx=helpers.MockContext(channel=self.bot_commands, author=self.non_staff_member)
            ),
            # `redirect` should be added implicitly to the `channels`
            WhitelistedContextTestCase(
                kwargs={"redirect": self.bot_commands.id},
                ctx=helpers.MockContext(channel=self.bot_commands, author=self.non_staff_member)
            ),

            # Commands issued in a whitelisted category by members without whitelisted roles
            WhitelistedContextTestCase(
                kwargs={"categories": self.categories},
                ctx=helpers.MockContext(channel=self.help_channel, author=self.non_staff_member)
            ),

            # Command issued by a staff member in a non-whitelisted channel/category
            WhitelistedContextTestCase(
                kwargs={"roles": self.roles},
                ctx=helpers.MockContext(channel=self.non_whitelisted_channel, author=self.staff_member)
            ),

            # With all kwargs provided
            WhitelistedContextTestCase(
                kwargs={
                    "channels": self.channels,
                    "categories": self.categories,
                    "roles": self.roles,
                    "redirect": self.bot_commands,
                },
                ctx=helpers.MockContext(channel=self.help_channel, author=self.staff_member)
            ),
        )

        for test_case in test_cases:
            # patch `commands.check` with a no-op lambda that just returns the predicate passed to it
            # so we can test the predicate that was generated from the specified kwargs.
            with unittest.mock.patch("bot.decorators.commands.check", new=lambda predicate: predicate):
                predicate = in_whitelist(**test_case.kwargs)

            with self.subTest(test_case=test_case):
                self.assertTrue(predicate(test_case.ctx))

    def test_predicate_raises_exception_for_non_whitelisted_context(self):
        """The predicate should raise `InWhitelistCheckFailure` for a non-whitelisted context."""
        test_cases = (
            # Failing check with `redirect`
            WhitelistedContextTestCase(
                kwargs={
                    "categories": self.categories,
                    "channels": self.channels,
                    "roles": self.roles,
                    "redirect": self.bot_commands.id,
                },
                ctx=helpers.MockContext(channel=self.non_whitelisted_channel, author=self.non_staff_member)
            ),

            # Failing check without `redirect`
            WhitelistedContextTestCase(
                kwargs={
                    "categories": self.categories,
                    "channels": self.channels,
                    "roles": self.roles,
                },
                ctx=helpers.MockContext(channel=self.non_whitelisted_channel, author=self.non_staff_member)
            ),
        )

        for test_case in test_cases:
            # Create expected exception message based on whether or not a redirect channel was provided
            expected_message = "Sorry, but you are not allowed to use that command here."
            if test_case.kwargs.get("redirect"):
                expected_message += f" Please use the <#{test_case.kwargs['redirect']}> channel instead."

            # patch `commands.check` with a no-op lambda that just returns the predicate passed to it
            # so we can test the predicate that was generated from the specified kwargs.
            with unittest.mock.patch("bot.decorators.commands.check", new=lambda predicate: predicate):
                predicate = in_whitelist(**test_case.kwargs)

            with self.subTest(test_case=test_case):
                with self.assertRaises(InWhitelistCheckFailure, msg=expected_message):
                    predicate(test_case.ctx)
