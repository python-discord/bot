import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bot.exts.moderation.clean import Clean
from tests.helpers import MockBot, MockContext, MockGuild, MockMember, MockMessage, MockRole, MockTextChannel


class CleanTests(unittest.IsolatedAsyncioTestCase):
    """Tests for clean cog functionality."""

    def setUp(self):
        self.bot = MockBot()
        self.mod = MockMember(roles=[MockRole(id=7890123, position=10)])
        self.user = MockMember(roles=[MockRole(id=123456, position=1)])
        self.guild = MockGuild()
        self.ctx = MockContext(bot=self.bot, author=self.mod)
        self.cog = Clean(self.bot)

        self.log_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.cog._modlog_cleaned_messages = AsyncMock(return_value=self.log_url)

        self.cog._use_cache = MagicMock(return_value=True)
        self.cog._delete_found = AsyncMock(return_value=[42, 84])

    @patch("bot.exts.moderation.clean.is_mod_channel")
    async def test_clean_deletes_invocation_in_non_mod_channel(self, mod_channel_check):
        """Clean command should delete the invocation message if ran in a non mod channel."""
        mod_channel_check.return_value = False
        self.ctx.message.delete = AsyncMock()

        self.assertIsNone(await self.cog._delete_invocation(self.ctx))

        self.ctx.message.delete.assert_awaited_once()

    @patch("bot.exts.moderation.clean.is_mod_channel")
    async def test_clean_doesnt_delete_invocation_in_mod_channel(self, mod_channel_check):
        """Clean command should not delete the invocation message if ran in a mod channel."""
        mod_channel_check.return_value = True
        self.ctx.message.delete = AsyncMock()

        self.assertIsNone(await self.cog._delete_invocation(self.ctx))

        self.ctx.message.delete.assert_not_awaited()

    async def test_clean_doesnt_attempt_deletion_when_attempt_delete_invocation_is_false(self):
        """Clean command should not attempt to delete the invocation message if attempt_delete_invocation is false."""
        self.cog._delete_invocation = AsyncMock()
        self.bot.get_channel = MagicMock(return_value=False)

        self.assertEqual(
            await self.cog._clean_messages(
                self.ctx,
                None,
                first_limit=MockMessage(),
                attempt_delete_invocation=False,
            ),
            self.log_url,
        )

        self.cog._delete_invocation.assert_not_awaited()

    @patch("bot.exts.moderation.clean.is_mod_channel")
    async def test_clean_replies_with_success_message_when_ran_in_mod_channel(self, mod_channel_check):
        """Clean command should reply to the message with a confirmation message if invoked in a mod channel."""
        mod_channel_check.return_value = True
        self.ctx.reply = AsyncMock()

        self.assertEqual(
            await self.cog._clean_messages(
                self.ctx,
                None,
                first_limit=MockMessage(),
                attempt_delete_invocation=False,
            ),
            self.log_url,
        )

        self.ctx.reply.assert_awaited_once()
        sent_message = self.ctx.reply.await_args[0][0]
        self.assertIn(self.log_url, sent_message)
        self.assertIn("2 messages", sent_message)

    @patch("bot.exts.moderation.clean.is_mod_channel")
    async def test_clean_send_success_message_to_mods_when_ran_in_non_mod_channel(self, mod_channel_check):
        """Clean command should send a confirmation message to #mods if invoked in a non-mod channel."""
        mod_channel_check.return_value = False
        mocked_mods = MockTextChannel(id=1234567)
        mocked_mods.send = AsyncMock()
        self.bot.get_channel = MagicMock(return_value=mocked_mods)

        self.assertEqual(
            await self.cog._clean_messages(
                self.ctx,
                None,
                first_limit=MockMessage(),
                attempt_delete_invocation=False,
            ),
            self.log_url,
        )

        mocked_mods.send.assert_awaited_once()
        sent_message = mocked_mods.send.await_args[0][0]
        self.assertIn(self.log_url, sent_message)
        self.assertIn("2 messages", sent_message)
