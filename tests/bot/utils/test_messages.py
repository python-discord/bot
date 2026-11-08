import unittest
import unittest.mock

import discord

from bot.utils import messages
from tests import helpers


class TestMessages(unittest.TestCase):
    """Tests for functions in the `bot.utils.messages` module."""

    def test_sub_clyde(self):
        """Uppercase E's and lowercase e's are substituted with their cyrillic counterparts."""
        sub_e = "\u0435"
        # N806 fires for upper-case E in variable name.
        sub_E = "\u0415"  # noqa: N806

        test_cases = (
            (None, None),
            ("", ""),
            ("clyde", f"clyd{sub_e}"),
            ("CLYDE", f"CLYD{sub_E}"),
            ("cLyDe", f"cLyD{sub_e}"),
            ("BIGclyde", f"BIGclyd{sub_e}"),
            ("small clydeus the unholy", f"small clyd{sub_e}us the unholy"),
            ("BIGCLYDE, babyclyde", f"BIGCLYD{sub_E}, babyclyd{sub_e}"),
        )

        for username_in, username_out in test_cases:
            with self.subTest(input=username_in, expected_output=username_out):
                self.assertEqual(messages.sub_clyde(username_in), username_out)


class TestWaitForDeletion(unittest.IsolatedAsyncioTestCase):
    """Tests for `wait_for_deletion`."""

    def setUp(self):
        patcher = unittest.mock.patch("bot.utils.messages.bot")
        self.bot = patcher.start().instance
        self.bot.wait_for = unittest.mock.AsyncMock()
        self.addCleanup(patcher.stop)

    async def test_slash_followup_without_guild_is_allowed(self):
        """A slash command followup has no guild info but is in a channel of unknown type, so it can be deleted."""
        message = helpers.MockMessage(guild=None, channel=helpers.MockTextChannel(type=None))
        message.add_reaction = unittest.mock.AsyncMock()
        message.delete = unittest.mock.AsyncMock()

        await messages.wait_for_deletion(message, (1,))

        message.add_reaction.assert_awaited_once()
        message.delete.assert_awaited_once()

    async def test_private_channel_is_rejected(self):
        """Messages in DMs can't be made deletable."""
        message = helpers.MockMessage(guild=None, channel=helpers.MockDMChannel(type=discord.ChannelType.private))

        with self.assertRaises(ValueError):
            await messages.wait_for_deletion(message, (1,))
