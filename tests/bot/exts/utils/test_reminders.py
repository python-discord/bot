import unittest
from datetime import UTC, datetime, timedelta
from unittest import mock

import discord

from bot import constants
from bot.exts.utils import reminders
from tests import helpers


class RemindMeMenuTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the Remind me message context menu."""

    def setUp(self):
        self.bot = helpers.MockBot()
        self.cog = reminders.Reminders(self.bot)
        self.message = helpers.MockMessage(content="Remember this", jump_url="https://discord.com/channels/1/2/3")

    def test_menu_is_guild_only_message_menu(self):
        menu = self.cog.remind_me_menu
        self.assertEqual(menu.type, discord.AppCommandType.message)
        self.assertTrue(menu.guild_only)

    async def test_menu_opens_modal_after_gating(self):
        interaction, ctx = helpers.make_menu_interaction(self.cog.remind_group.get_command("new"))
        interaction.response.send_modal = mock.AsyncMock()

        with mock.patch.object(reminders, "authorise_command", mock.AsyncMock(return_value=ctx)) as authorise:
            await self.cog._remind_me_menu_callback(interaction, self.message)

        authorise.assert_awaited_once_with(interaction, "remind new")
        modal = interaction.response.send_modal.await_args.args[0]
        self.assertIsInstance(modal, reminders.RemindMeModal)

    async def test_menu_denied_does_not_open_modal(self):
        interaction = helpers.MockInteraction()
        interaction.response.send_modal = mock.AsyncMock()

        with (
            mock.patch.object(reminders, "authorise_command", mock.AsyncMock(side_effect=ValueError)),
            self.assertRaises(ValueError),
        ):
            await self.cog._remind_me_menu_callback(interaction, self.message)

        interaction.response.send_modal.assert_not_called()

    async def _submit(self, duration: str) -> tuple[mock.Mock, helpers.MockInteraction]:
        ctx = helpers.MockContext()
        ctx.defer = mock.AsyncMock()
        modal = reminders.RemindMeModal(self.cog, ctx, self.message)
        modal.duration._value = duration
        modal_interaction = helpers.MockInteraction()
        modal_interaction.response = mock.Mock(send_message=mock.AsyncMock())
        self.cog.create_reminder = mock.AsyncMock()
        await modal.on_submit(modal_interaction)
        return ctx, modal_interaction

    async def test_invalid_duration_is_rejected_ephemerally(self):
        _, interaction = await self._submit("not a duration")

        interaction.response.send_message.assert_awaited_once()
        self.assertTrue(interaction.response.send_message.await_args.kwargs["ephemeral"])
        self.cog.create_reminder.assert_not_called()

    async def test_valid_duration_creates_reminder_for_the_message(self):
        ctx, interaction = await self._submit("3d")

        self.assertIs(ctx.interaction, interaction)
        self.cog.create_reminder.assert_awaited_once_with(
            ctx,
            mentions=[],
            expiration=mock.ANY,
            content="Remember this",
            jump_url="https://discord.com/channels/1/2/3",
        )

    async def test_non_staff_outside_whitelisted_channel_is_denied(self):
        """The creation logic shared with the command denies members outside the allowed channels."""
        self.bot.api_client.post = mock.AsyncMock()
        ctx = helpers.MockContext(channel=helpers.MockTextChannel(id=42))
        ctx.author.roles = []

        with mock.patch.object(reminders, "send_denial", mock.AsyncMock()) as send_denial:
            await reminders.Reminders.create_reminder(
                self.cog, ctx, [], mock.Mock(), "content", "https://discord.com/channels/1/2/3"
            )

        send_denial.assert_awaited_once()
        self.bot.api_client.post.assert_not_called()

    async def test_staff_can_create_reminder_anywhere(self):
        self.bot.api_client.post = mock.AsyncMock(return_value={"id": 1})
        ctx = helpers.MockContext(channel=helpers.MockTextChannel(id=42))
        ctx.author.roles = [helpers.MockRole(id=constants.Roles.helpers)]
        self.cog._send_confirmation = mock.AsyncMock()
        self.cog.schedule_reminder = mock.Mock()
        expiration = datetime.now(UTC) + timedelta(days=1)

        with mock.patch.object(reminders, "OptInReminderMentionView", mock.Mock(return_value=mock.AsyncMock())):
            await reminders.Reminders.create_reminder(
                self.cog, ctx, [], expiration, "content", "https://discord.com/channels/1/2/3"
            )

        sent = self.bot.api_client.post.await_args.kwargs["json"]
        self.assertEqual(sent["jump_url"], "https://discord.com/channels/1/2/3")
        self.assertEqual(sent["content"], "content")
