from typing import Iterable

from bot.rules import chars
from tests.bot.rules import DisallowedCase, RuleTest
from tests.helpers import MockMessage


def make_msg(author: str, n_chars: int) -> MockMessage:
    """Build a message with arbitrary content of `n_chars` length."""
    return MockMessage(author=author, content="A" * n_chars)


class CharsRuleTests(RuleTest):
    """Tests the `chars` antispam rule."""

    def setUp(self):
        self.apply = chars.apply
        self.config = {
            "max": 20,  # Max allowed sum of chars per user
            "interval": 10,
        }

    async def test_allows_messages_within_limit(self):
        """Cases with a total amount of chars within limit."""
        cases = (
            [make_msg("bob", 0)],
            [make_msg("bob", 20)],
            [make_msg("bob", 15), make_msg("alice", 15)],
        )

        await self.run_allowed(cases)

    async def test_disallows_messages_beyond_limit(self):
        """Cases where the total amount of chars exceeds the limit, triggering the rule."""
        cases = (
            DisallowedCase(
                [make_msg("bob", 21)],
                ("bob",),
                21,
            ),
            DisallowedCase(
                [make_msg("bob", 15), make_msg("bob", 15)],
                ("bob",),
                30,
            ),
            DisallowedCase(
                [make_msg("alice", 15), make_msg("bob", 20), make_msg("alice", 15)],
                ("alice",),
                30,
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
        return f"sent {case.n_violations} characters in {self.config['interval']}s"
