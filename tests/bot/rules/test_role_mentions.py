import unittest

from bot.rules import role_mentions
from tests.helpers import MockMessage, async_test


def make_msg(author: str, n_mentions: int) -> MockMessage:
    """Build a MockMessage instance with `n_mentions` role mentions."""
    return MockMessage(author=author, role_mentions=[None] * n_mentions)


class RoleMentionsRuleTests(unittest.TestCase):
    """Tests for the `role_mentions` antispam rule."""

    def setUp(self):
        self.config = {"max": 2, "interval": 10}

    @async_test
    async def test_allows_messages_within_limit(self):
        """Cases with a total amount of role mentions within limit."""
        cases = (
            [make_msg("bob", 2)],
            [make_msg("bob", 1), make_msg("alice", 1), make_msg("bob", 1)],
        )

        for recent_messages in cases:
            last_message = recent_messages[0]

            with self.subTest(last_message=last_message, recent_messages=recent_messages, config=self.config):
                self.assertIsNone(await role_mentions.apply(last_message, recent_messages, self.config))

    @async_test
    async def test_disallows_messages_beyond_limit(self):
        """Cases with more than the allowed amount of role mentions."""
        cases = (
            (
                [make_msg("bob", 3)],
                "bob",
                3,
            ),
            (
                [make_msg("alice", 2), make_msg("bob", 2), make_msg("alice", 2)],
                "alice",
                4,
            ),
        )

        for recent_messages, culprit, total_mentions in cases:
            last_message = recent_messages[0]
            relevant_messages = tuple(msg for msg in recent_messages if msg.author == culprit)
            expected_output = (
                f"sent {total_mentions} role mentions in {self.config['interval']}s",
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
                    await role_mentions.apply(last_message, recent_messages, self.config),
                    expected_output,
                )
