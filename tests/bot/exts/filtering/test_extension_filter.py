import unittest
from unittest.mock import MagicMock, patch

import arrow

from bot.constants import Channels
from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filter_lists import extension
from bot.exts.filtering._filter_lists.extension import ExtensionsList
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
                "id": i, "content": filter_content, "description": None, "settings": {},
                "additional_settings": {}, "created_at": now, "updated_at": now
            })
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
    async def test_python_file_redirect_embed_description(self):
        """A message containing a .py file should result in an embed redirecting the user to our paste site."""
        attachment = MockAttachment(filename="python.py")
        ctx = self.ctx.replace(attachments=[attachment])

        await self.filter_list.actions_for(ctx)

        self.assertEqual(ctx.dm_embed, extension.PY_EMBED_DESCRIPTION)

    @patch("bot.instance", BOT)
    async def test_txt_file_redirect_embed_description(self):
        """A message containing a .txt/.json/.csv file should result in the correct embed."""
        test_values = (
            ("text", ".txt"),
            ("json", ".json"),
            ("csv", ".csv"),
        )

        for file_name, disallowed_extension in test_values:
            with self.subTest(file_name=file_name, disallowed_extension=disallowed_extension):

                attachment = MockAttachment(filename=f"{file_name}{disallowed_extension}")
                ctx = self.ctx.replace(attachments=[attachment])

                await self.filter_list.actions_for(ctx)

                self.assertEqual(
                    ctx.dm_embed,
                    extension.TXT_EMBED_DESCRIPTION.format(
                        blocked_extension=disallowed_extension,
                    )
                )

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
