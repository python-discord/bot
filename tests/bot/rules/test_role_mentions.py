from typing import Iterable

from bot.rules import role_mentions
from tests.bot.rules import DisallowedCase, RuleTest
from tests.helpers import MockMessage


def make_msg(author: str, n_mentions: int) -> MockMessage:
    """Build a MockMessage instance with `n_mentions` role mentions."""
    return MockMessage(author=author, role_mentions=[None] * n_mentions)


class RoleMentionsRuleTests(RuleTest):
    """Tests for the `role_mentions` antispam rule."""

    def setUp(self):
        self.apply = role_mentions.apply
        self.config = {"max": 2, "interval": 10}

    async def test_allows_messages_within_limit(self):
        """Cases with a total amount of role mentions within limit."""
        cases = (
            [make_msg("bob", 2)],
            [make_msg("bob", 1), make_msg("alice", 1), make_msg("bob", 1)],
        )

        await self.run_allowed(cases)

    async def test_disallows_messages_beyond_limit(self):
        """Cases with more than the allowed amount of role mentions."""
        cases = (
            DisallowedCase(
                [make_msg("bob", 3)],
                ("bob",),
                3,
            ),
            DisallowedCase(
                [make_msg("alice", 2), make_msg("bob", 2), make_msg("alice", 2)],
                ("alice",),
                4,
            ),
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
        return f"sent {case.n_violations} role mentions in {self.config['interval']}s"
