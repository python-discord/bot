import unittest
from typing import List, NamedTuple, Tuple

from bot.rules import mentions
from tests.helpers import async_test


class FakeMessage(NamedTuple):
    author: str
    mentions: List[None]


class Case(NamedTuple):
    recent_messages: List[FakeMessage]
    relevant_messages: Tuple[FakeMessage]
    culprit: str
    total_mentions: int


def msg(author: str, total_mentions: int) -> FakeMessage:
    """Makes a message with `total_mentions` mentions."""
    return FakeMessage(author=author, mentions=list(range(total_mentions)))


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
            [msg("bob", 0)],
            [msg("bob", 2)],
            [msg("bob", 1), msg("bob", 1)],
            [msg("bob", 1), msg("alice", 2)]
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
                [msg("bob", 3)],
                (msg("bob", 3),),
                ("bob",),
                3
            ),
            Case(
                [msg("alice", 2), msg("alice", 0), msg("alice", 1)],
                (msg("alice", 2), msg("alice", 0), msg("alice", 1)),
                ("alice",),
                3
            ),
            Case(
                [msg("bob", 2), msg("alice", 3), msg("bob", 2)],
                (msg("bob", 2), msg("bob", 2)),
                ("bob",),
                4
            )
        )

        for recent_messages, relevant_messages, culprit, total_mentions in cases:
            last_message = recent_messages[0]

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
