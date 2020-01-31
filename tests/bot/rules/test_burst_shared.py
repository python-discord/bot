import unittest

from bot.rules import burst_shared
from tests.helpers import MockMessage, async_test


def make_msg(author: str) -> MockMessage:
    """
    Init a MockMessage instance with the passed arg.

    This serves as a shorthand / alias to keep the test cases visually clean.
    """
    return MockMessage(author=author)


class BurstSharedRuleTests(unittest.TestCase):
    """Tests the `burst_shared` antispam rule."""

    def setUp(self):
        self.config = {"max": 2, "interval": 10}

    @async_test
    async def test_allows_messages_within_limit(self):
        """
        Cases that do not violate the rule.

        There really isn't more to test here than a single case.
        """
        recent_messages = [make_msg("spongebob"), make_msg("patrick")]
        last_message = recent_messages[0]

        self.assertIsNone(await burst_shared.apply(last_message, recent_messages, self.config))

    @async_test
    async def test_disallows_messages_beyond_limit(self):
        """Cases where the amount of messages exceeds the limit, triggering the rule."""
        cases = (
            (
                [make_msg("bob"), make_msg("bob"), make_msg("bob")],
                {"bob"},
                3,
            ),
            (
                [make_msg("bob"), make_msg("bob"), make_msg("alice"), make_msg("bob")],
                {"bob", "alice"},
                4,
            ),
        )

        for recent_messages, culprits, total_msgs in cases:
            last_message = recent_messages[0]
            expected_output = (
                f"sent {total_msgs} messages in {self.config['interval']}s",
                culprits,
                recent_messages,
            )

            with self.subTest(
                last_message=last_message,
                recent_messages=recent_messages,
                config=self.config,
                expected_output=expected_output,
            ):
                self.assertTupleEqual(
                    await burst_shared.apply(last_message, recent_messages, self.config),
                    expected_output,
                )
