from typing import Iterable

from bot.rules import duplicates
from tests.bot.rules import DisallowedCase, RuleTest
from tests.helpers import MockMessage


def make_msg(author: str, content: str) -> MockMessage:
    """Give a MockMessage instance with `author` and `content` attrs."""
    return MockMessage(author=author, content=content)


class DuplicatesRuleTests(RuleTest):
    """Tests the `duplicates` antispam rule."""

    def setUp(self):
        self.apply = duplicates.apply
        self.config = {"max": 2, "interval": 10}

    async def test_allows_messages_within_limit(self):
        """Cases which do not violate the rule."""
        cases = (
            [make_msg("alice", "A"), make_msg("alice", "A")],
            [make_msg("alice", "A"), make_msg("alice", "B"), make_msg("alice", "C")],  # Non-duplicate
            [make_msg("alice", "A"), make_msg("bob", "A"), make_msg("alice", "A")],  # Different author
        )

        await self.run_allowed(cases)

    async def test_disallows_messages_beyond_limit(self):
        """Cases with too many duplicate messages from the same author."""
        cases = (
            DisallowedCase(
                [make_msg("alice", "A"), make_msg("alice", "A"), make_msg("alice", "A")],
                ("alice",),
                3,
            ),
            DisallowedCase(
                [make_msg("bob", "A"), make_msg("alice", "A"), make_msg("bob", "A"), make_msg("bob", "A")],
                ("bob",),
                3,  # 4 duplicate messages, but only 3 from bob
            ),
            DisallowedCase(
                [make_msg("bob", "A"), make_msg("bob", "B"), make_msg("bob", "A"), make_msg("bob", "A")],
                ("bob",),
                3,  # 4 message from bob, but only 3 duplicates
            ),
        )

        await self.run_disallowed(cases)

    def relevant_messages(self, case: DisallowedCase) -> Iterable[MockMessage]:
        last_message = case.recent_messages[0]
        return tuple(
            msg
            for msg in case.recent_messages
            if (
                msg.author == last_message.author
                and msg.content == last_message.content
            )
        )

    def get_report(self, case: DisallowedCase) -> str:
        return f"sent {case.n_violations} duplicated messages in {self.config['interval']}s"
