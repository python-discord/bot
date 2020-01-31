import unittest

from bot.rules import burst
from tests.helpers import MockMessage, async_test


def make_msg(author: str) -> MockMessage:
    """
    Init a MockMessage instance with author set to `author`.

    This serves as a shorthand / alias to keep the test cases visually clean.
    """
    return MockMessage(author=author)


class BurstRuleTests(unittest.TestCase):
    """Tests the `burst` antispam rule."""

    def setUp(self):
        self.config = {"max": 2, "interval": 10}

    @async_test
    async def test_allows_messages_within_limit(self):
        """Cases which do not violate the rule."""
        cases = (
            [make_msg("bob"), make_msg("bob")],
            [make_msg("bob"), make_msg("alice"), make_msg("bob")],
        )

        for recent_messages in cases:
            last_message = recent_messages[0]

            with self.subTest(last_message=last_message, recent_messages=recent_messages, config=self.config):
                self.assertIsNone(await burst.apply(last_message, recent_messages, self.config))

    @async_test
    async def test_disallows_messages_beyond_limit(self):
        """Cases where the amount of messages exceeds the limit, triggering the rule."""
        cases = (
            (
                [make_msg("bob"), make_msg("bob"), make_msg("bob")],
                "bob",
                3,
            ),
            (
                [make_msg("bob"), make_msg("bob"), make_msg("alice"), make_msg("bob")],
                "bob",
                3,
            ),
        )

        for recent_messages, culprit, total_msgs in cases:
            last_message = recent_messages[0]
            relevant_messages = tuple(msg for msg in recent_messages if msg.author == culprit)
            expected_output = (
                f"sent {total_msgs} messages in {self.config['interval']}s",
                (culprit,),
                relevant_messages,
            )

            with self.subTest(
                last_message=last_message,
                recent_messages=recent_messages,
                config=self.config,
                expected_output=expected_output,
            ):
                self.assertTupleEqual(
                    await burst.apply(last_message, recent_messages, self.config),
                    expected_output,
                )
