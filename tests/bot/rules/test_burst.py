from typing import Iterable

from bot.rules import burst
from tests.bot.rules import DisallowedCase, RuleTest
from tests.helpers import MockMessage


def make_msg(author: str) -> MockMessage:
    """
    Init a MockMessage instance with author set to `author`.

    This serves as a shorthand / alias to keep the test cases visually clean.
    """
    return MockMessage(author=author)


class BurstRuleTests(RuleTest):
    """Tests the `burst` antispam rule."""

    def setUp(self):
        self.apply = burst.apply
        self.config = {"max": 2, "interval": 10}

    async def test_allows_messages_within_limit(self):
        """Cases which do not violate the rule."""
        cases = (
            [make_msg("bob"), make_msg("bob")],
            [make_msg("bob"), make_msg("alice"), make_msg("bob")],
        )

        await self.run_allowed(cases)

    async def test_disallows_messages_beyond_limit(self):
        """Cases where the amount of messages exceeds the limit, triggering the rule."""
        cases = (
            DisallowedCase(
                [make_msg("bob"), make_msg("bob"), make_msg("bob")],
                ("bob",),
                3,
            ),
            DisallowedCase(
                [make_msg("bob"), make_msg("bob"), make_msg("alice"), make_msg("bob")],
                ("bob",),
                3,
            ),
        )

        await self.run_disallowed(cases)

    def relevant_messages(self, case: DisallowedCase) -> Iterable[MockMessage]:
        return tuple(msg for msg in case.recent_messages if msg.author in case.culprits)

    def get_report(self, case: DisallowedCase) -> str:
        return f"sent {case.n_violations} messages in {self.config['interval']}s"
