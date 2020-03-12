from typing import Iterable

from bot.rules import links
from tests.bot.rules import DisallowedCase, RuleTest
from tests.helpers import MockMessage


def make_msg(author: str, total_links: int) -> MockMessage:
    """Makes a message with `total_links` links."""
    content = " ".join(["https://pydis.com"] * total_links)
    return MockMessage(author=author, content=content)


class LinksTests(RuleTest):
    """Tests applying the `links` rule."""

    def setUp(self):
        self.apply = links.apply
        self.config = {
            "max": 2,
            "interval": 10
        }

    async def test_links_within_limit(self):
        """Messages with an allowed amount of links."""
        cases = (
            [make_msg("bob", 0)],
            [make_msg("bob", 2)],
            [make_msg("bob", 3)],  # Filter only applies if len(messages_with_links) > 1
            [make_msg("bob", 1), make_msg("bob", 1)],
            [make_msg("bob", 2), make_msg("alice", 2)]  # Only messages from latest author count
        )

        await self.run_allowed(cases)

    async def test_links_exceeding_limit(self):
        """Messages with a a higher than allowed amount of links."""
        cases = (
            DisallowedCase(
                [make_msg("bob", 1), make_msg("bob", 2)],
                ("bob",),
                3
            ),
            DisallowedCase(
                [make_msg("alice", 1), make_msg("alice", 1), make_msg("alice", 1)],
                ("alice",),
                3
            ),
            DisallowedCase(
                [make_msg("alice", 2), make_msg("bob", 3), make_msg("alice", 1)],
                ("alice",),
                3
            )
        )

        await self.run_disallowed(cases)

    def relevant_messages(self, case: DisallowedCase) -> Iterable[MockMessage]:
        last_message = case.recent_messages[0]
        return tuple(
            msg
            for msg in case.recent_messages
            if msg.author == last_message.author
        )

    def get_report(self, case: DisallowedCase) -> str:
        return f"sent {case.n_violations} links in {self.config['interval']}s"
