import asyncio
import unittest

from bot.rules import attachments
from tests.helpers import MockMessage


def msg(total_attachments: int) -> MockMessage:
    """Builds a message with `total_attachments` attachments."""
    return MockMessage(author='lemon', attachments=list(range(total_attachments)))


class AttachmentRuleTests(unittest.TestCase):
    """Tests applying the `attachments` antispam rule."""

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
            ([msg(4), msg(0), msg(6)], 10),
            ([msg(6)], 6),
            ([msg(1)] * 6, 6),
        )
        for messages, total in cases:
            last_message, *recent_messages = messages
            relevant_messages = [last_message] + [
                msg
                for msg in recent_messages
                if msg.author == last_message.author
                and len(msg.attachments) > 0
            ]

            with self.subTest(
                last_message=last_message,
                recent_messages=recent_messages,
                relevant_messages=relevant_messages,
                total=total
            ):
                coro = attachments.apply(last_message, recent_messages, {'max': 5})
                self.assertEqual(
                    asyncio.run(coro),
                    (f"sent {total} attachments in 5s", ('lemon',), relevant_messages)
                )
