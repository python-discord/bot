from typing import Iterable

from bot.rules import burst_shared
from tests.bot.rules import DisallowedCase, RuleTest
from tests.helpers import MockMessage


def make_msg(author: str) -> MockMessage:
    """
    Init a MockMessage instance with the passed arg.

    This serves as a shorthand / alias to keep the test cases visually clean.
    """
    return MockMessage(author=author)


class BurstSharedRuleTests(RuleTest):
    """Tests the `burst_shared` antispam rule."""

    def setUp(self):
        self.apply = burst_shared.apply
        self.config = {"max": 2, "interval": 10}

    async def test_allows_messages_within_limit(self):
        """
        Cases that do not violate the rule.

        There really isn't more to test here than a single case.
        """
        cases = (
            [make_msg("spongebob"), make_msg("patrick")],
        )

        await self.run_allowed(cases)

    async def test_disallows_messages_beyond_limit(self):
        """Cases where the amount of messages exceeds the limit, triggering the rule."""
        cases = (
            DisallowedCase(
                [make_msg("bob"), make_msg("bob"), make_msg("bob")],
                {"bob"},
                3,
            ),
            DisallowedCase(
                [make_msg("bob"), make_msg("bob"), make_msg("alice"), make_msg("bob")],
                {"bob", "alice"},
                4,
            ),
        )

        await self.run_disallowed(cases)

    def relevant_messages(self, case: DisallowedCase) -> Iterable[MockMessage]:
        return case.recent_messages

    def get_report(self, case: DisallowedCase) -> str:
        return f"sent {case.n_violations} messages in {self.config['interval']}s"
