import asyncio
import unittest
from dataclasses import dataclass
from typing import Any, List

from bot.rules import attachments


# Using `MagicMock` sadly doesn't work for this usecase
# since it's __eq__ compares the MagicMock's ID. We just
# want to compare the actual attributes we set.
@dataclass
class FakeMessage:
    author: str
    attachments: List[Any]


def msg(total_attachments: int) -> FakeMessage:
    return FakeMessage(author='lemon', attachments=list(range(total_attachments)))


class AttachmentRuleTests(unittest.TestCase):
    """Tests applying the `attachment` antispam rule."""

    def test_allows_messages_without_too_many_attachments(self):
        """Messages without too many attachments are allowed as-is."""
        cases = (
            (msg(0), msg(0), msg(0)),
            (msg(2), msg(2)),
            (msg(0),),
        )

        for last_message, *recent_messages in cases:
            with self.subTest(last_message=last_message, recent_messages=recent_messages):
                coro = attachments.apply(last_message, recent_messages, {'max': 5})
                self.assertIsNone(asyncio.run(coro))

    def test_disallows_messages_with_too_many_attachments(self):
        """Messages with too many attachments trigger the rule."""
        cases = (
            ((msg(4), msg(0), msg(6)), [msg(4), msg(6)], 10),
            ((msg(6),), [msg(6)], 6),
            ((msg(1),) * 6, [msg(1)] * 6, 6),
        )
        for messages, relevant_messages, total in cases:
            with self.subTest(messages=messages, relevant_messages=relevant_messages, total=total):
                last_message, *recent_messages = messages
                coro = attachments.apply(last_message, recent_messages, {'max': 5})
                self.assertEqual(
                    asyncio.run(coro),
                    (f"sent {total} attachments in 5s", ('lemon',), relevant_messages)
                )
