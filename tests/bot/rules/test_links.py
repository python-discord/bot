import unittest
from typing import List, NamedTuple, Tuple

from bot.rules import links
from tests.helpers import MockMessage, async_test


class Case(NamedTuple):
    recent_messages: List[MockMessage]
    culprit: Tuple[str]
    total_links: int


def make_msg(author: str, total_links: int) -> MockMessage:
    """Makes a message with `total_links` links."""
    content = " ".join(["https://pydis.com"] * total_links)
    return MockMessage(author=author, content=content)


class LinksTests(unittest.TestCase):
    """Tests applying the `links` rule."""

    def setUp(self):
        self.config = {
            "max": 2,
            "interval": 10
        }

    @async_test
    async def test_links_within_limit(self):
        """Messages with an allowed amount of links."""
        cases = (
            [make_msg("bob", 0)],
            [make_msg("bob", 2)],
            [make_msg("bob", 3)],  # Filter only applies if len(messages_with_links) > 1
            [make_msg("bob", 1), make_msg("bob", 1)],
            [make_msg("bob", 2), make_msg("alice", 2)]  # Only messages from latest author count
        )

        for recent_messages in cases:
            last_message = recent_messages[0]

            with self.subTest(
                last_message=last_message,
                recent_messages=recent_messages,
                config=self.config
            ):
                self.assertIsNone(
                    await links.apply(last_message, recent_messages, self.config)
                )

    @async_test
    async def test_links_exceeding_limit(self):
        """Messages with a a higher than allowed amount of links."""
        cases = (
            Case(
                [make_msg("bob", 1), make_msg("bob", 2)],
                ("bob",),
                3
            ),
            Case(
                [make_msg("alice", 1), make_msg("alice", 1), make_msg("alice", 1)],
                ("alice",),
                3
            ),
            Case(
                [make_msg("alice", 2), make_msg("bob", 3), make_msg("alice", 1)],
                ("alice",),
                3
            )
        )

        for recent_messages, culprit, total_links in cases:
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
                total_links=total_links,
                config=self.config
            ):
                desired_output = (
                    f"sent {total_links} links in {self.config['interval']}s",
                    culprit,
                    relevant_messages
                )
                self.assertTupleEqual(
                    await links.apply(last_message, recent_messages, self.config),
                    desired_output
                )
