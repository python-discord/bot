from typing import Iterable

from bot.rules import everyone_ping
from tests.bot.rules import DisallowedCase, RuleTest
from tests.helpers import MockGuild, MockMessage

NUM_GUILD_MEMBERS = 100


def make_msg(author: str, message: str) -> MockMessage:
    """Build a message with `message` as the content sent."""
    mocked_guild = MockGuild(member_count=NUM_GUILD_MEMBERS)
    return MockMessage(author=author, content=message, guild=mocked_guild)


class EveryonePingRuleTest(RuleTest):
    """Tests the `everyone_ping` antispam rule."""

    def setUp(self):
        self.apply = everyone_ping.apply
        self.config = {
            "max": 0,  # Max allowed @everyone pings per user
            "interval": 10,
        }

    async def test_disallows_everyone_ping(self):
        """Cases with an @everyone ping."""
        cases = (
            DisallowedCase(
                [make_msg("bob", "@everyone")],
                ("bob",),
                1
            ),
            DisallowedCase(
                [make_msg("bob", "Let me ping @everyone in the server.")],
                ("bob",),
                1
            ),
            DisallowedCase(
                [make_msg("bob", "`codeblock message` and @everyone ping")],
                ("bob",),
                1
            ),
            DisallowedCase(
                [make_msg("bob", "`sandwich` @everyone `ping between codeblocks`.")],
                ("bob",),
                1
            ),
            DisallowedCase(
                [make_msg("bob", "This is a multiline\n@everyone\nping.")],
                ("bob",),
                1
            ),
            # Not actually valid code blocks
            DisallowedCase(
                [make_msg("bob", "`@everyone``")],
                ("bob",),
                1
            ),
            DisallowedCase(
                [make_msg("bob", "`@everyone``````")],
                ("bob",),
                1
            ),
            DisallowedCase(
                [make_msg("bob", "``@everyone``````")],
                ("bob",),
                1
            ),
        )

        await self.run_disallowed(cases)

    async def test_allows_inline_codeblock_everyone_ping(self):
        """Cases with an @everyone ping in an inline codeblock."""
        cases = (
            [make_msg("bob", "Codeblock has `@everyone` ping.")],
            [make_msg("bob", "Multiple `codeblocks` including `@everyone` ping.")],
            [make_msg("bob", "This is a valid ``inline @everyone` ping.")],
        )

        await self.run_allowed(cases)

    async def test_allows_multiline_codeblock_everyone_ping(self):
        """Cases with an @everyone ping in a multiline codeblock."""
        cases = (
            [make_msg("bob", "```Multiline codeblock has\nan `@everyone` ping.```")],
            [make_msg("bob", "``` `@everyone``` ` `")],
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
        return "pinged the everyone role"
