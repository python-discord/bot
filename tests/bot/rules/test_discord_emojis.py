import unittest

from bot.rules import discord_emojis
from tests.helpers import MockMessage, async_test

discord_emoji = "<:abcd:1234>"  # Discord emojis follow the format <:name:id>


def make_msg(author: str, n_emojis: int) -> MockMessage:
    """Build a MockMessage instance with content containing `n_emojis` arbitrary emojis."""
    return MockMessage(author=author, content=discord_emoji * n_emojis)


class DiscordEmojisRuleTests(unittest.TestCase):
    """Tests for the `discord_emojis` antispam rule."""

    def setUp(self):
        self.config = {"max": 2, "interval": 10}

    @async_test
    async def test_allows_messages_within_limit(self):
        """Cases with a total amount of discord emojis within limit."""
        cases = (
            [make_msg("bob", 2)],
            [make_msg("alice", 1), make_msg("bob", 2), make_msg("alice", 1)],
        )

        for recent_messages in cases:
            last_message = recent_messages[0]

            with self.subTest(last_message=last_message, recent_messages=recent_messages, config=self.config):
                self.assertIsNone(await discord_emojis.apply(last_message, recent_messages, self.config))

    @async_test
    async def test_disallows_messages_beyond_limit(self):
        """Cases with more than the allowed amount of discord emojis."""
        cases = (
            (
                [make_msg("bob", 3)],
                "bob",
                3,
            ),
            (
                [make_msg("alice", 2), make_msg("bob", 2), make_msg("alice", 2)],
                "alice",
                4,
            ),
        )

        for recent_messages, culprit, total_emojis in cases:
            last_message = recent_messages[0]
            relevant_messages = tuple(msg for msg in recent_messages if msg.author == culprit)
            expected_output = (
                f"sent {total_emojis} emojis in {self.config['interval']}s",
                (culprit,),
                relevant_messages,
            )

            with self.subTest(
                last_message=last_message,
                recent_messages=recent_messages,
                config=self.config,
                expected_output=expected_output,
            ):
                self.assertTupleEqual(
                    await discord_emojis.apply(last_message, recent_messages, self.config),
                    expected_output,
                )
