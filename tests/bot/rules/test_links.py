import unittest
from typing import List, NamedTuple, Tuple

from bot.rules import links
from tests.helpers import async_test


class FakeMessage(NamedTuple):
    author: str
    content: str


class Case(NamedTuple):
    recent_messages: List[FakeMessage]
    relevant_messages: Tuple[FakeMessage]
    culprit: Tuple[str]
    total_links: int


def msg(author: str, total_links: int) -> FakeMessage:
    """Makes a message with `total_links` links."""
    content = " ".join(["https://pydis.com"] * total_links)
    return FakeMessage(author=author, content=content)


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
            [msg("bob", 0)],
            [msg("bob", 2)],
            [msg("bob", 3)],
            [msg("bob", 3), msg("alice", 3)]
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
                [msg("bob", 1), msg("bob", 2)],
                (msg("bob", 1), msg("bob", 2)),
                ("bob",),
                3
            ),
            Case(
                [msg("alice", 2), msg("bob", 3), msg("alice", 1)],
                (msg("alice", 2), msg("alice", 1)),
                ("alice",),
                3
            )
        )

        for recent_messages, relevant_messages, culprit, total_links in cases:
            last_message = recent_messages[0]

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
