import unittest
from unittest.mock import MagicMock, patch

import arrow

from bot.constants import Channels
from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filter_lists import extension
from bot.exts.filtering._filter_lists.extension import ExtensionsList, PY_EMBED_DESCRIPTION, TXT_EMBED_DESCRIPTION
from bot.exts.filtering._filter_lists.filter_list import ListType
from tests.helpers import MockAttachment, MockBot, MockMember, MockMessage, MockTextChannel

BOT = MockBot()


class ExtensionsListTests(unittest.IsolatedAsyncioTestCase):
    """Test the ExtensionsList class."""

    def setUp(self):
        """Sets up fresh objects for each test."""
        self.filter_list = ExtensionsList(MagicMock())
        now = arrow.utcnow().timestamp()
        filters = []
        self.whitelist = [".first", ".second", ".third"]
        for i, filter_content in enumerate(self.whitelist, start=1):
            filters.append({
                "id": i,
                "content": filter_content,
                "description": None,
                "settings": {},
                "additional_settings": {},
                "created_at": now,
                "updated_at": now
            })
        # Add the ALLOW list (id=1 => ListType.ALLOW)
        self.filter_list.add_list({
            "id": 1,
            "list_type": 1,
            "created_at": now,
            "updated_at": now,
            "settings": {},
            "filters": filters
        })

        self.message = MockMessage()
        member = MockMember(id=123)
        channel = MockTextChannel(id=345)
        self.ctx = FilterContext(Event.MESSAGE, member, channel, "", self.message)

    @patch("bot.instance", BOT)
    async def test_message_with_allowed_attachment(self):
        """Messages with allowed extensions should trigger the whitelist and result in no actions or messages."""
        attachment = MockAttachment(filename="python.first")
        ctx = self.ctx.replace(attachments=[attachment])

        result = await self.filter_list.actions_for(ctx)

        self.assertEqual(result, (None, [], {ListType.ALLOW: [self.filter_list[ListType.ALLOW].filters[1]]}))

    @patch("bot.instance", BOT)
    async def test_message_without_attachment(self):
        """Messages without attachments should return no triggers, messages, or actions."""
        result = await self.filter_list.actions_for(self.ctx)

        self.assertEqual(result, (None, [], {}))

    @patch("bot.instance", BOT)
    async def test_message_with_illegal_extension(self):
        """A message with an illegal extension shouldn't trigger the whitelist, and return some action and message."""
        attachment = MockAttachment(filename="python.disallowed")
        ctx = self.ctx.replace(attachments=[attachment])

        result = await self.filter_list.actions_for(ctx)

        self.assertEqual(result, ({}, ["`.disallowed`"], {ListType.ALLOW: []}))

    @patch("bot.instance", BOT)
    async def test_other_disallowed_extension_embed_description(self):
        """Test the description for a non .py/.txt/.json/.csv disallowed extension."""
        attachment = MockAttachment(filename="python.disallowed")
        ctx = self.ctx.replace(attachments=[attachment])

        await self.filter_list.actions_for(ctx)
        meta_channel = BOT.get_channel(Channels.meta)

        self.assertEqual(
            ctx.dm_embed,
            extension.DISALLOWED_EMBED_DESCRIPTION.format(
                joined_whitelist=", ".join(self.whitelist),
                joined_blacklist=".disallowed",
                meta_channel_mention=meta_channel.mention
            )
        )

    @patch("bot.instance", BOT)
    async def test_get_disallowed_extensions(self):
        """The return value should include all non-whitelisted extensions."""
        test_values = (
            ([], []),
            (self.whitelist, []),
            ([".first"], []),
            ([".first", ".disallowed"], ["`.disallowed`"]),
            ([".disallowed"], ["`.disallowed`"]),
            ([".disallowed", ".illegal"], ["`.disallowed`", "`.illegal`"]),
        )

        for extensions, expected_disallowed_extensions in test_values:
            with self.subTest(extensions=extensions, expected_disallowed_extensions=expected_disallowed_extensions):
                ctx = self.ctx.replace(attachments=[MockAttachment(filename=f"filename{ext}") for ext in extensions])
                result = await self.filter_list.actions_for(ctx)
                self.assertCountEqual(result[1], expected_disallowed_extensions)

    @patch("bot.instance", BOT)
    async def test_disallowed_py_extension_sets_py_embed(self):
        """A .py file that's not in the ALLOW list should trigger PY_EMBED_DESCRIPTION."""
        attachment = MockAttachment(filename="script.py")
        ctx = self.ctx.replace(attachments=[attachment])

        actions, blocked_exts, triggered_filters = await self.filter_list.actions_for(ctx)

        self.assertEqual(ctx.dm_embed, PY_EMBED_DESCRIPTION, "Expected the PY_EMBED_DESCRIPTION for disallowed .py")
        # Typically, disallowed extension -> non-empty blocked_exts, no ALLOW filters triggered
        self.assertIn("`.py`", blocked_exts, "Blocked extensions should include `.py`")
        self.assertEqual(triggered_filters[ListType.ALLOW], [], "No ALLOW filters should match a .py extension")


    @patch("bot.instance", BOT)
    async def test_disallowed_txt_extension_sets_txt_embed(self):
        """A .txt file that's not whitelisted should trigger TXT_EMBED_DESCRIPTION."""
        attachment = MockAttachment(filename="notes.txt")
        ctx = self.ctx.replace(attachments=[attachment])

        actions, blocked_exts, triggered_filters = await self.filter_list.actions_for(ctx)

        self.assertEqual(ctx.dm_embed, TXT_EMBED_DESCRIPTION.format(blocked_extension=".txt"),
                         "Expected the TXT_EMBED_DESCRIPTION for disallowed text-like file")
        self.assertIn("`.txt`", blocked_exts, "Blocked extensions should include `.txt`")
        self.assertEqual(triggered_filters[ListType.ALLOW], [], "No ALLOW filters should match .txt if it's unlisted")

    @patch("bot.instance", BOT)
    async def test_snekbox_textlike_file_not_blocked(self):
        """
        In SNEKBOX mode, text-like attachments (e.g., .txt) aren't blocked,
        so no embed should be set and the result should show no blocked extensions.
        """
        attachment = MockAttachment(filename="script.txt")
        snekbox_ctx = self.ctx.replace(event=Event.SNEKBOX, attachments=[attachment])

        actions, blocked_exts, triggered_filters = await self.filter_list.actions_for(snekbox_ctx)

        self.assertEqual(snekbox_ctx.dm_embed, "", "Should not set a DM embed for text-like file in SNEKBOX mode.")
        self.assertEqual(actions, None, "No blocking actions for .txt in SNEKBOX.")
        self.assertEqual(blocked_exts, [], "No blocked extensions in SNEKBOX for text-like files.")
        self.assertIn(ListType.ALLOW, triggered_filters, "We at least check the allow list, even if empty.")

    @patch("bot.instance", BOT)
    async def test_no_message_object_returns_early(self):
        """If ctx.message is None, the function should return (None, [], {}) immediately."""
        no_msg_ctx = self.ctx.replace(message=None)

        result = await self.filter_list.actions_for(no_msg_ctx)

        self.assertEqual(result, (None, [], {}), "Expected early return if ctx.message is None.")
