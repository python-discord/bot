import unittest
from unittest import mock

import discord

from bot.constants import MODERATION_ROLES, Roles
from bot.exts.filtering import filtering
from bot.utils.context_menus import ContextMenuDenied
from tests import helpers


class FilteringMenuTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the Filter match and Filter imagehash message context menus."""

    def setUp(self):
        self.cog = filtering.Filtering(helpers.MockBot())
        # Commands only have their cog set once the cog is added to a bot.
        for command in (self.cog.filter, self.cog.f_match, self.cog.f_imagehash):
            command.cog = self.cog
        self.message = helpers.MockMessage(content="some text", attachments=[], embeds=[])

    def test_menus_are_guild_only_message_menus(self):
        for menu in self.cog.context_menus:
            with self.subTest(menu=menu.name):
                self.assertEqual(menu.type, discord.AppCommandType.message)
                self.assertTrue(menu.guild_only)
                self.assertLessEqual(len(menu.name), 32)

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

    async def test_imagehash_non_moderator_denied(self):
        interaction, _ = self._interaction(self.cog.f_imagehash, ())
        self.cog._reply_with_image_hash = mock.AsyncMock()

        with self.assertRaises(ContextMenuDenied):
            await self.cog._filter_imagehash_menu_callback(interaction, self.message)

        self.cog._reply_with_image_hash.assert_not_called()

    async def test_imagehash_uses_first_image_attachment(self):
        interaction, ctx = self._interaction(self.cog.f_imagehash, (MODERATION_ROLES[0],))
        self.cog._reply_with_image_hash = mock.AsyncMock()
        text = mock.Mock(content_type="text/plain", url="text", size=1)
        image = mock.Mock(content_type="image/png", url="image", size=2)
        self.message.attachments = [text, image]

        await self.cog._filter_imagehash_menu_callback(interaction, self.message)

        self.cog._reply_with_image_hash.assert_awaited_once_with(ctx, "image", 2)

    async def test_imagehash_falls_back_to_embed_image(self):
        interaction, ctx = self._interaction(self.cog.f_imagehash, (MODERATION_ROLES[0],))
        self.cog._reply_with_image_hash = mock.AsyncMock()
        self.message.embeds = [discord.Embed().set_image(url="https://example.com/a.png")]

        await self.cog._filter_imagehash_menu_callback(interaction, self.message)

        self.cog._reply_with_image_hash.assert_awaited_once_with(ctx, "https://example.com/a.png", None)

    async def test_imagehash_without_image(self):
        interaction, ctx = self._interaction(self.cog.f_imagehash, (MODERATION_ROLES[0],))
        self.cog._reply_with_image_hash = mock.AsyncMock()

        await self.cog._filter_imagehash_menu_callback(interaction, self.message)

        self.cog._reply_with_image_hash.assert_not_called()
        ctx.send.assert_awaited_once()

    async def test_oversized_image_is_rejected(self):
        ctx = helpers.MockContext()
        ctx.reply = mock.AsyncMock()

        with mock.patch.object(filtering, "get_image_hash", mock.AsyncMock()) as get_hash:
            await self.cog._reply_with_image_hash(ctx, "url", filtering.MAX_IMAGE_HASH_SIZE + 1)

        get_hash.assert_not_called()
        ctx.reply.assert_awaited_once()
