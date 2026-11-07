import unittest
from unittest import mock

import discord

from bot.constants import MODERATION_ROLES, Roles
from bot.exts.filtering import filtering
from bot.utils.context_menus import ContextMenuDenied
from tests import helpers


class FilteringMenuTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the Filter match message context menu."""

    def setUp(self):
        self.cog = filtering.Filtering(helpers.MockBot())
        # Commands only have their cog set once the cog is added to a bot.
        for command in (self.cog.filter, self.cog.f_match):
            command.cog = self.cog
        self.message = helpers.MockMessage(content="some text", attachments=[], embeds=[])

    def test_menu_is_guild_only_message_menu(self):
        menu = self.cog.filter_match_menu
        self.assertEqual(menu.type, discord.AppCommandType.message)
        self.assertTrue(menu.guild_only)

    def _interaction(self, command, role_ids):
        interaction, ctx = helpers.make_menu_interaction(command, role_ids=role_ids)
        ctx.defer = mock.AsyncMock()
        ctx.send = mock.AsyncMock()
        ctx.reply = mock.AsyncMock()
        return interaction, ctx

    async def test_match_moderator_allowed(self):
        interaction, ctx = self._interaction(self.cog.f_match, (MODERATION_ROLES[0],))
        self.cog._get_match_lines = mock.AsyncMock(return_value=["**Filters**", "filter 1"])

        await self.cog._filter_match_menu_callback(interaction, self.message)

        ctx.defer.assert_awaited_once_with(ephemeral=True)
        embed = ctx.send.await_args.kwargs["embed"]
        self.assertIn("filter 1", embed.description)

    async def test_match_with_no_triggers(self):
        interaction, ctx = self._interaction(self.cog.f_match, (MODERATION_ROLES[0],))
        self.cog._get_match_lines = mock.AsyncMock(return_value=[])

        await self.cog._filter_match_menu_callback(interaction, self.message)

        self.assertEqual(ctx.send.await_args.kwargs["embed"].description, "No filters were triggered.")

    async def test_match_non_moderator_denied(self):
        interaction, ctx = self._interaction(self.cog.f_match, (Roles.helpers,))
        self.cog._get_match_lines = mock.AsyncMock()

        with self.assertRaises(ContextMenuDenied):
            await self.cog._filter_match_menu_callback(interaction, self.message)

        self.cog._get_match_lines.assert_not_called()
        ctx.defer.assert_not_called()
