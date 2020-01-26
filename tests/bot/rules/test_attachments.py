import unittest
from typing import List, NamedTuple, Tuple

from bot.rules import attachments
from tests.helpers import MockMessage, async_test


class Case(NamedTuple):
    recent_messages: List[MockMessage]
    culprit: Tuple[str]
    total_attachments: int


def make_msg(author: str, total_attachments: int) -> MockMessage:
    """Builds a message with `total_attachments` attachments."""
    return MockMessage(author=author, attachments=list(range(total_attachments)))


class AttachmentRuleTests(unittest.TestCase):
    """Tests applying the `attachments` antispam rule."""

    def setUp(self):
        self.config = {"max": 5, "interval": 10}

    @async_test
    async def test_allows_messages_without_too_many_attachments(self):
        """Messages without too many attachments are allowed as-is."""
        cases = (
            [make_msg("bob", 0), make_msg("bob", 0), make_msg("bob", 0)],
            [make_msg("bob", 2), make_msg("bob", 2)],
            [make_msg("bob", 2), make_msg("alice", 2), make_msg("bob", 2)],
        )

        for recent_messages in cases:
            last_message = recent_messages[0]

            with self.subTest(
                last_message=last_message,
                recent_messages=recent_messages,
                config=self.config
            ):
                self.assertIsNone(
                    await attachments.apply(last_message, recent_messages, self.config)
                )

    @async_test
    async def test_disallows_messages_with_too_many_attachments(self):
        """Messages with too many attachments trigger the rule."""
        cases = (
            Case(
                [make_msg("bob", 4), make_msg("bob", 0), make_msg("bob", 6)],
                ("bob",),
                10
            ),
            Case(
                [make_msg("bob", 4), make_msg("alice", 6), make_msg("bob", 2)],
                ("bob",),
                6
            ),
            Case(
                [make_msg("alice", 6)],
                ("alice",),
                6
            ),
            (
                [make_msg("alice", 1) for _ in range(6)],
                ("alice",),
                6
            ),
        )

        for recent_messages, culprit, total_attachments in cases:
            last_message = recent_messages[0]
            relevant_messages = tuple(
                msg
                for msg in recent_messages
                if (
                    msg.author == last_message.author
                    and len(msg.attachments) > 0
                )
            )

            with self.subTest(
                last_message=last_message,
                recent_messages=recent_messages,
                relevant_messages=relevant_messages,
                total_attachments=total_attachments,
                config=self.config
            ):
                desired_output = (
                    f"sent {total_attachments} attachments in {self.config['interval']}s",
                    culprit,
                    relevant_messages
                )
                self.assertTupleEqual(
                    await attachments.apply(last_message, recent_messages, self.config),
                    desired_output
                )
