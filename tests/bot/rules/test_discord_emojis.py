from typing import Iterable

from bot.rules import discord_emojis
from tests.bot.rules import DisallowedCase, RuleTest
from tests.helpers import MockMessage

discord_emoji = "<:abcd:1234>"  # Discord emojis follow the format <:name:id>
unicode_emoji = "🧪"


def make_msg(author: str, n_emojis: int, emoji: str = discord_emoji) -> MockMessage:
    """Build a MockMessage instance with content containing `n_emojis` arbitrary emojis."""
    return MockMessage(author=author, content=emoji * n_emojis)


class DiscordEmojisRuleTests(RuleTest):
    """Tests for the `discord_emojis` antispam rule."""

    def setUp(self):
        self.apply = discord_emojis.apply
        self.config = {"max": 2, "interval": 10}

    async def test_allows_messages_within_limit(self):
        """Cases with a total amount of discord and unicode emojis within limit."""
        cases = (
            [make_msg("bob", 2)],
            [make_msg("alice", 1), make_msg("bob", 2), make_msg("alice", 1)],
            [make_msg("bob", 2, unicode_emoji)],
            [
                make_msg("alice", 1, unicode_emoji),
                make_msg("bob", 2, unicode_emoji),
                make_msg("alice", 1, unicode_emoji)
            ],
        )

        await self.run_allowed(cases)

    async def test_disallows_messages_beyond_limit(self):
        """Cases with more than the allowed amount of discord and unicode emojis."""
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
            DisallowedCase(
                [make_msg("bob", 3, unicode_emoji)],
                ("bob",),
                3,
            ),
            DisallowedCase(
                [
                    make_msg("alice", 2, unicode_emoji),
                    make_msg("bob", 2, unicode_emoji),
                    make_msg("alice", 2, unicode_emoji)
                ],
                ("alice",),
                4
            )
        )

        await self.run_disallowed(cases)

    def relevant_messages(self, case: DisallowedCase) -> Iterable[MockMessage]:
        return tuple(msg for msg in case.recent_messages if msg.author in case.culprits)

    def get_report(self, case: DisallowedCase) -> str:
        return f"sent {case.n_violations} emojis in {self.config['interval']}s"
