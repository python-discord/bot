import unittest
from unittest import mock

import discord

from bot.constants import MODERATION_ROLES, Roles
from bot.exts.moderation.watchchannels import bigbrother
from bot.utils.context_menus import ContextMenuDenied
from tests import helpers


class WatchMenuTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the Watch / Unwatch user context menu."""

    def setUp(self):
        self.cog = bigbrother.BigBrother(helpers.MockBot())
        # Commands only have their cog set once the cog is added to a bot.
        for command in (self.cog.bigbrother_group, self.cog.watch_command, self.cog.unwatch_command):
            command.cog = self.cog
        self.target = helpers.MockMember(id=42)

    def _interaction(self, role_ids=(MODERATION_ROLES[0],)):
        interaction, ctx = helpers.make_menu_interaction(None, role_ids=role_ids)
        commands = {"bigbrother watch": self.cog.watch_command, "bigbrother unwatch": self.cog.unwatch_command}
        interaction.client.get_command.side_effect = commands.get
        interaction.response = mock.Mock(send_modal=mock.AsyncMock())
        ctx.defer = mock.AsyncMock()
        ctx.invoke = mock.AsyncMock()
        return interaction, ctx

    def test_menu_is_guild_only_user_menu(self):
        menu = self.cog.watch_menu
        self.assertEqual(menu.type, discord.AppCommandType.user)
        self.assertTrue(menu.guild_only)
        self.assertLessEqual(len(menu.name), 32)

    async def test_unwatched_user_opens_watch_modal(self):
        interaction, ctx = self._interaction()

        await self.cog._watch_menu_callback(interaction, self.target)

        modal = interaction.response.send_modal.await_args.args[0]
        self.assertEqual(modal.command_name, "bigbrother watch")
        self.assertIs(ctx.command, self.cog.watch_command)

    async def test_watched_user_opens_unwatch_modal(self):
        interaction, ctx = self._interaction()
        self.cog.watched_users[self.target.id] = {}

        await self.cog._watch_menu_callback(interaction, self.target)

        modal = interaction.response.send_modal.await_args.args[0]
        self.assertEqual(modal.command_name, "bigbrother unwatch")
        self.assertIs(ctx.command, self.cog.unwatch_command)

    async def test_non_moderator_is_denied_for_both(self):
        for watched in (False, True):
            with self.subTest(watched=watched):
                interaction, _ = self._interaction(role_ids=(Roles.helpers,))
                self.cog.watched_users = {self.target.id: {}} if watched else {}

                with self.assertRaises(ContextMenuDenied):
                    await self.cog._watch_menu_callback(interaction, self.target)

                interaction.response.send_modal.assert_not_called()

    async def test_submit_runs_command_after_deferring(self):
        interaction, ctx = self._interaction()
        modal = bigbrother.WatchModal(ctx, self.target, watching=False)
        modal.reason._value = "  suspicious  "

        await modal.on_submit(interaction)

        self.assertIs(ctx.interaction, interaction)
        ctx.defer.assert_awaited_once()
        ctx.invoke.assert_awaited_once_with(self.cog.watch_command, self.target, reason="suspicious")

    async def test_submit_after_losing_the_role_is_denied(self):
        interaction, ctx = self._interaction()
        modal = bigbrother.WatchModal(ctx, self.target, watching=True)
        modal.reason._value = "reason"
        ctx.author.roles = []

        with self.assertRaises(ContextMenuDenied):
            await modal.on_submit(interaction)

        ctx.invoke.assert_not_called()
