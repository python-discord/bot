from typing import Iterable

from bot.rules import attachments
from tests.bot.rules import DisallowedCase, RuleTest
from tests.helpers import MockMessage


def make_msg(author: str, total_attachments: int) -> MockMessage:
    """Builds a message with `total_attachments` attachments."""
    return MockMessage(author=author, attachments=list(range(total_attachments)))


class AttachmentRuleTests(RuleTest):
    """Tests applying the `attachments` antispam rule."""

    def setUp(self):
        self.apply = attachments.apply
        self.config = {"max": 5, "interval": 10}

    async def test_allows_messages_without_too_many_attachments(self):
        """Messages without too many attachments are allowed as-is."""
        cases = (
            [make_msg("bob", 0), make_msg("bob", 0), make_msg("bob", 0)],
            [make_msg("bob", 2), make_msg("bob", 2)],
            [make_msg("bob", 2), make_msg("alice", 2), make_msg("bob", 2)],
        )

        await self.run_allowed(cases)

    async def test_disallows_messages_with_too_many_attachments(self):
        """Messages with too many attachments trigger the rule."""
        cases = (
            DisallowedCase(
                [make_msg("bob", 4), make_msg("bob", 0), make_msg("bob", 6)],
                ("bob",),
                10,
            ),
            DisallowedCase(
                [make_msg("bob", 4), make_msg("alice", 6), make_msg("bob", 2)],
                ("bob",),
                6,
            ),
            DisallowedCase(
                [make_msg("alice", 6)],
                ("alice",),
                6,
            ),
            DisallowedCase(
                [make_msg("alice", 1) for _ in range(6)],
                ("alice",),
                6,
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
                and len(msg.attachments) > 0
            )
        )

    def get_report(self, case: DisallowedCase) -> str:
        return f"sent {case.n_violations} attachments in {self.config['interval']}s"
