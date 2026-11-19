import unittest
from unittest import mock

import discord

from bot.constants import MODERATION_ROLES, Roles
from bot.exts.recruitment.talentpool import _cog
from bot.utils.context_menus import ContextMenuDenied
from tests import helpers


class HistoryMenuTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the Talentpool history user context menu."""

    def setUp(self):
        self.cog = _cog.TalentPool(helpers.MockBot())
        # Commands only have their cog set once the cog is added to a bot.
        self.cog.nomination_group.cog = self.cog
        self.cog.history_command.cog = self.cog
        self.target = helpers.MockMember(id=42)

    def _interaction(self, role_ids):
        interaction, ctx = helpers.make_menu_interaction(self.cog.history_command, role_ids=role_ids)
        ctx.defer = mock.AsyncMock()
        ctx.send = mock.AsyncMock()
        return interaction, ctx

    def test_menu_is_guild_only_user_menu(self):
        menu = self.cog.history_menu
        self.assertEqual(menu.type, discord.AppCommandType.user)
        self.assertTrue(menu.guild_only)
        self.assertLessEqual(len(menu.name), 32)

    async def test_moderator_sees_history_ephemerally(self):
        interaction, ctx = self._interaction((MODERATION_ROLES[0], Roles.helpers))
        self.cog._get_nomination_history = mock.AsyncMock(return_value=["first", "second"])

        await self.cog._history_menu_callback(interaction, self.target)

        ctx.defer.assert_awaited_once_with(ephemeral=True)
        embed = ctx.send.await_args.kwargs["embed"]
        self.assertEqual(embed.description, "first\n\nsecond")

    async def test_user_without_nominations(self):
        interaction, ctx = self._interaction((MODERATION_ROLES[0], Roles.helpers))
        self.cog._get_nomination_history = mock.AsyncMock(return_value=[])

        await self.cog._history_menu_callback(interaction, self.target)

        self.assertIn("never been nominated", ctx.send.await_args.args[0])

    async def test_helper_is_denied(self):
        """Helpers are staff, but only moderators may see the history."""
        interaction, ctx = self._interaction((Roles.helpers,))
        self.cog._get_nomination_history = mock.AsyncMock()

        with self.assertRaises(ContextMenuDenied):
            await self.cog._history_menu_callback(interaction, self.target)

        self.cog._get_nomination_history.assert_not_called()
        ctx.defer.assert_not_called()

    async def test_regular_member_is_denied(self):
        interaction, _ = self._interaction(())

        with self.assertRaises(ContextMenuDenied):
            await self.cog._history_menu_callback(interaction, self.target)

    def test_history_pages_fit_in_an_embed(self):
        size = _cog.HISTORY_PAGE_SIZE
        pages = self.cog._history_pages(["a" * (size - 10), "b" * 20, "c" * (size * 2 + 5)])

        self.assertTrue(all(len(page) <= size for page in pages))
        self.assertEqual("".join(pages).replace("\n", ""), "a" * (size - 10) + "b" * 20 + "c" * (size * 2 + 5))
