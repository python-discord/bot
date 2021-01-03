from typing import Iterable, List

from bot.rules import newlines
from tests.bot.rules import DisallowedCase, RuleTest
from tests.helpers import MockMessage


def make_msg(author: str, newline_groups: List[int]) -> MockMessage:
    """Init a MockMessage instance with `author` and content configured by `newline_groups".

    Configure content by passing a list of ints, where each int `n` will generate
    a separate group of `n` newlines.

    Example:
        newline_groups=[3, 1, 2] -> content="\n\n\n \n \n\n"
    """
    content = " ".join("\n" * n for n in newline_groups)
    return MockMessage(author=author, content=content)


class TotalNewlinesRuleTests(RuleTest):
    """Tests the `newlines` antispam rule against allowed cases and total newline count violations."""

    def setUp(self):
        self.apply = newlines.apply
        self.config = {
            "max": 5,  # Max sum of newlines in relevant messages
            "max_consecutive": 3,  # Max newlines in one group, in one message
            "interval": 10,
        }

    async def test_allows_messages_within_limit(self):
        """Cases which do not violate the rule."""
        cases = (
            [make_msg("alice", [])],  # Single message with no newlines
            [make_msg("alice", [1, 2]), make_msg("alice", [1, 1])],  # 5 newlines in 2 messages
            [make_msg("alice", [2, 2, 1]), make_msg("bob", [2, 3])],  # 5 newlines from each author
            [make_msg("bob", [1]), make_msg("alice", [5])],  # Alice breaks the rule, but only bob is relevant
        )

        await self.run_allowed(cases)

    async def test_disallows_messages_total(self):
        """Cases which violate the rule by having too many newlines in total."""
        cases = (
            DisallowedCase(  # Alice sends a total of 6 newlines (disallowed)
                [make_msg("alice", [2, 2]), make_msg("alice", [2])],
                ("alice",),
                6,
            ),
            DisallowedCase(  # Here we test that only alice's newlines count in the sum
                [make_msg("alice", [2, 2]), make_msg("bob", [3]), make_msg("alice", [3])],
                ("alice",),
                7,
            ),
        )

        await self.run_disallowed(cases)

    def relevant_messages(self, case: DisallowedCase) -> Iterable[MockMessage]:
        last_author = case.recent_messages[0].author
        return tuple(msg for msg in case.recent_messages if msg.author == last_author)

    def get_report(self, case: DisallowedCase) -> str:
        return f"sent {case.n_violations} newlines in {self.config['interval']}s"


class GroupNewlinesRuleTests(RuleTest):
    """
    Tests the `newlines` antispam rule against max consecutive newline violations.

    As these violations yield a different error report, they require a different
    `get_report` implementation.
    """

    def setUp(self):
        self.apply = newlines.apply
        self.config = {"max": 5, "max_consecutive": 3, "interval": 10}

    async def test_disallows_messages_consecutive(self):
        """Cases which violate the rule due to having too many consecutive newlines."""
        cases = (
            DisallowedCase(  # Bob sends a group of newlines too large
                [make_msg("bob", [4])],
                ("bob",),
                4,
            ),
            DisallowedCase(  # Alice sends 5 in total (allowed), but 4 in one group (disallowed)
                [make_msg("alice", [1]), make_msg("alice", [4])],
                ("alice",),
                4,
            ),
        )

        await self.run_disallowed(cases)

    def relevant_messages(self, case: DisallowedCase) -> Iterable[MockMessage]:
        last_author = case.recent_messages[0].author
        return tuple(msg for msg in case.recent_messages if msg.author == last_author)

    def get_report(self, case: DisallowedCase) -> str:
        return f"sent {case.n_violations} consecutive newlines in {self.config['interval']}s"
