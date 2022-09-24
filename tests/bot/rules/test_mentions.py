from typing import Iterable, Optional

import discord

from bot.rules import mentions
from tests.bot.rules import DisallowedCase, RuleTest
from tests.helpers import MockMember, MockMessage, MockMessageReference


def make_msg(
    author: str,
    total_user_mentions: int,
    total_bot_mentions: int = 0,
    *,
    reference: Optional[MockMessageReference] = None
) -> MockMessage:
    """Makes a message from `author` with `total_user_mentions` user mentions and `total_bot_mentions` bot mentions."""
    user_mentions = [MockMember() for _ in range(total_user_mentions)]
    bot_mentions = [MockMember(bot=True) for _ in range(total_bot_mentions)]

    mentions = user_mentions + bot_mentions
    if reference is not None:
        # For the sake of these tests we assume that all references are mentions.
        mentions.append(reference.resolved.author)
        msg_type = discord.MessageType.reply
    else:
        msg_type = discord.MessageType.default

    return MockMessage(author=author, mentions=mentions, reference=reference, type=msg_type)


class TestMentions(RuleTest):
    """Tests applying the `mentions` antispam rule."""

    def setUp(self):
        self.apply = mentions.apply
        self.config = {
            "max": 2,
            "interval": 10,
        }

    async def test_mentions_within_limit(self):
        """Messages with an allowed amount of mentions."""
        cases = (
            [make_msg("bob", 0)],
            [make_msg("bob", 2)],
            [make_msg("bob", 1), make_msg("bob", 1)],
            [make_msg("bob", 1), make_msg("alice", 2)],
        )

        await self.run_allowed(cases)

    async def test_mentions_exceeding_limit(self):
        """Messages with a higher than allowed amount of mentions."""
        cases = (
            DisallowedCase(
                [make_msg("bob", 3)],
                ("bob",),
                3,
            ),
            DisallowedCase(
                [make_msg("alice", 2), make_msg("alice", 0), make_msg("alice", 1)],
                ("alice",),
                3,
            ),
            DisallowedCase(
                [make_msg("bob", 2), make_msg("alice", 3), make_msg("bob", 2)],
                ("bob",),
                4,
            ),
            DisallowedCase(
                [make_msg("bob", 3, 1)],
                ("bob",),
                3,
            ),
            DisallowedCase(
                [make_msg("bob", 3, reference=MockMessageReference())],
                ("bob",),
                3,
            ),
            DisallowedCase(
                [make_msg("bob", 3, reference=MockMessageReference(reference_author_is_bot=True))],
                ("bob",),
                3
            )
        )

        await self.run_disallowed(cases)

    async def test_ignore_bot_mentions(self):
        """Messages with an allowed amount of mentions, also containing bot mentions."""
        cases = (
            [make_msg("bob", 0, 3)],
            [make_msg("bob", 2, 1)],
            [make_msg("bob", 1, 2), make_msg("bob", 1, 2)],
            [make_msg("bob", 1, 5), make_msg("alice", 2, 5)]
        )

        await self.run_allowed(cases)

    async def test_ignore_reply_mentions(self):
        """Messages with an allowed amount of mentions in the content, also containing reply mentions."""
        cases = (
            [
                make_msg("bob", 2, reference=MockMessageReference())
            ],
            [
                make_msg("bob", 2, reference=MockMessageReference(reference_author_is_bot=True))
            ],
            [
                make_msg("bob", 2, reference=MockMessageReference()),
                make_msg("bob", 0, reference=MockMessageReference())
            ],
            [
                make_msg("bob", 2, reference=MockMessageReference(reference_author_is_bot=True)),
                make_msg("bob", 0, reference=MockMessageReference(reference_author_is_bot=True))
            ]
        )

        await self.run_allowed(cases)

    def relevant_messages(self, case: DisallowedCase) -> Iterable[MockMessage]:
        last_message = case.recent_messages[0]
        return tuple(
            msg
            for msg in case.recent_messages
            if msg.author == last_message.author
        )

    def get_report(self, case: DisallowedCase) -> str:
        return f"sent {case.n_violations} mentions in {self.config['interval']}s"
