import unittest

from bot.rules import chars
from tests.helpers import MockMessage, async_test


def make_msg(author: str, n_chars: int) -> MockMessage:
    """Build a message with arbitrary content of `n_chars` length."""
    return MockMessage(author=author, content="A" * n_chars)


class CharsRuleTests(unittest.TestCase):
    """Tests the `chars` antispam rule."""

    def setUp(self):
        self.config = {
            "max": 20,  # Max allowed sum of chars per user
            "interval": 10,
        }

    @async_test
    async def test_allows_messages_within_limit(self):
        """Cases with a total amount of chars within limit."""
        cases = (
            [make_msg("bob", 0)],
            [make_msg("bob", 20)],
            [make_msg("bob", 15), make_msg("alice", 15)],
        )

        for recent_messages in cases:
            last_message = recent_messages[0]

            with self.subTest(last_message=last_message, recent_messages=recent_messages, config=self.config):
                self.assertIsNone(await chars.apply(last_message, recent_messages, self.config))

    @async_test
    async def test_disallows_messages_beyond_limit(self):
        """Cases where the total amount of chars exceeds the limit, triggering the rule."""
        cases = (
            (
                [make_msg("bob", 21)],
                "bob",
                21,
            ),
            (
                [make_msg("bob", 15), make_msg("bob", 15)],
                "bob",
                30,
            ),
            (
                [make_msg("alice", 15), make_msg("bob", 20), make_msg("alice", 15)],
                "alice",
                30,
            ),
        )

        for recent_messages, culprit, total_chars in cases:
            last_message = recent_messages[0]
            relevant_messages = tuple(msg for msg in recent_messages if msg.author == culprit)
            expected_output = (
                f"sent {total_chars} characters in {self.config['interval']}s",
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
                    await chars.apply(last_message, recent_messages, self.config),
                    expected_output,
                )
