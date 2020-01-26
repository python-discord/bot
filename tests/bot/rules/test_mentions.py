import unittest
from typing import List, NamedTuple, Tuple

from bot.rules import mentions
from tests.helpers import MockMessage, async_test


class Case(NamedTuple):
    recent_messages: List[MockMessage]
    culprit: Tuple[str]
    total_mentions: int


def make_msg(author: str, total_mentions: int) -> MockMessage:
    """Makes a message with `total_mentions` mentions."""
    return MockMessage(author=author, mentions=list(range(total_mentions)))


class TestMentions(unittest.TestCase):
    """Tests applying the `mentions` antispam rule."""

    def setUp(self):
        self.config = {
            "max": 2,
            "interval": 10
        }

    @async_test
    async def test_mentions_within_limit(self):
        """Messages with an allowed amount of mentions."""
        cases = (
            [make_msg("bob", 0)],
            [make_msg("bob", 2)],
            [make_msg("bob", 1), make_msg("bob", 1)],
            [make_msg("bob", 1), make_msg("alice", 2)]
        )

        for recent_messages in cases:
            last_message = recent_messages[0]

            with self.subTest(
                last_message=last_message,
                recent_messages=recent_messages,
                config=self.config
            ):
                self.assertIsNone(
                    await mentions.apply(last_message, recent_messages, self.config)
                )

    @async_test
    async def test_mentions_exceeding_limit(self):
        """Messages with a higher than allowed amount of mentions."""
        cases = (
            Case(
                [make_msg("bob", 3)],
                ("bob",),
                3
            ),
            Case(
                [make_msg("alice", 2), make_msg("alice", 0), make_msg("alice", 1)],
                ("alice",),
                3
            ),
            Case(
                [make_msg("bob", 2), make_msg("alice", 3), make_msg("bob", 2)],
                ("bob",),
                4
            )
        )

        for recent_messages, culprit, total_mentions in cases:
            last_message = recent_messages[0]
            relevant_messages = tuple(
                msg
                for msg in recent_messages
                if msg.author == last_message.author
            )

            with self.subTest(
                last_message=last_message,
                recent_messages=recent_messages,
                relevant_messages=relevant_messages,
                culprit=culprit,
                total_mentions=total_mentions,
                cofig=self.config
            ):
                desired_output = (
                    f"sent {total_mentions} mentions in {self.config['interval']}s",
                    culprit,
                    relevant_messages
                )
                self.assertTupleEqual(
                    await mentions.apply(last_message, recent_messages, self.config),
                    desired_output
                )
