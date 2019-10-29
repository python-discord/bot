import asyncio
import unittest
from dataclasses import dataclass
from typing import Optional

from bot.rules import newlines


# Using `MagicMock` sadly doesn't work for this usecase
# since it's __eq__ compares the MagicMock's ID. We just
# want to compare the actual attributes we set.
@dataclass
class FakeMessage:
    author: str
    content: str


def msg(new_lines: int, consecutive_new_lines: int, base_content: Optional[str] = "sample msg") -> FakeMessage:
    content = base_content
    content += "a\n" * new_lines
    content += "\n" * consecutive_new_lines
    return FakeMessage(author='lemon', content=content)


class AttachmentRuleTests(unittest.TestCase):
    """Tests applying the `attachment` antispam rule."""

    def test_allows_messages_without_too_many_newlines(self):
        """Messages without too many newlines are allowed as-is."""
        cases = (
            (msg(0, 0), msg(0, 0), msg(0, 0)),
            (msg(5, 0), msg(5, 0)),
            (msg(3, 2), msg(3, 2)),
            (msg(0, 5), msg(0, 5)),
            (msg(10, 0), msg(0, 0)),
            ((msg(1, 0),) * 10),
            ((msg(0, 1),) * 10),
            ((msg(0, 1, base_content=''),) * 11),
            (msg(0, 0),),
        )

        for last_message, *recent_messages in cases:
            with self.subTest(last_message=last_message, recent_messages=recent_messages):
                coro = newlines.apply(last_message, recent_messages, {'max': 10, 'max_consecutive': 5, 'interval': 5})
                self.assertIsNone(asyncio.run(coro))

    def test_disallows_messages_with_too_many_newlines(self):
        """Messages with too many newlines trigger the rule."""
        cases = (
            ((msg(4, 0), msg(4, 0), msg(7, 0)), (msg(4, 0), msg(7, 0),), 11),
            ((msg(2, 0), msg(12, 0)), (msg(12, 0),), 12),
            ((msg(2, 0), msg(12, 12)), (msg(12, 12),), 24),
            ((msg(1, 0),) * 14, (msg(1, 0),) * 13, 13),
        )
        for messages, relevant_messages, total in cases:
            with self.subTest(messages=messages, relevant_messages=relevant_messages, total=total):
                last_message, *recent_messages = messages
                coro = newlines.apply(last_message, recent_messages, {'max': 10, 'max_consecutive': 5, 'interval': 5})
                self.assertEqual(
                    asyncio.run(coro),
                    (f"sent {total} newlines in 5s", ('lemon',), relevant_messages)
                )

    def test_disallows_messages_with_too_many_consecutive_newlines(self):
        """Messages with too many consecutive newlines trigger the rule."""
        cases = (
            ((msg(1, 0), msg(0, 6), msg(0, 2)), (msg(0, 6), msg(0, 2),), 6),
            ((msg(2, 0), msg(0, 2), msg(1, 0), msg(0, 6)), (msg(0, 2), msg(1, 0), msg(0, 6),), 6),
            ((msg(2, 0), msg(0, 7)), (msg(0, 7),), 7),
            ((msg(0, 8),) * 2, (msg(0, 8),), 8),
        )
        for messages, relevant_messages, total in cases:
            with self.subTest(messages=messages, relevant_messages=relevant_messages, total=total):
                last_message, *recent_messages = messages
                coro = newlines.apply(last_message, recent_messages, {'max': 10, 'max_consecutive': 5, 'interval': 5})
                self.assertEqual(
                    asyncio.run(coro),
                    (f"sent {total} consecutive newlines in 5s", ('lemon',), relevant_messages)
                )
