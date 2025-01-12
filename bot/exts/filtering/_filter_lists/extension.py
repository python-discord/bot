from __future__ import annotations

import logging
import re
import typing
from os.path import splitext

import aiohttp
import discord
from discord.ext import commands
from pydis_core.utils import paste_service

import bot
from bot.bot import Bot
from bot.constants import Channels, Emojis
from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filter_lists.filter_list import FilterList, ListType
from bot.exts.filtering._filters.extension import ExtensionFilter
from bot.exts.filtering._filters.filter import Filter
from bot.exts.filtering._settings import ActionSettings

if typing.TYPE_CHECKING:
    from bot.exts.filtering.filtering import Filtering

PASTE_URL = "https://paste.pythondiscord.com"
PY_EMBED_DESCRIPTION = (
    "It looks like you tried to attach a Python file - "
    f"please use a code-pasting service such as {PASTE_URL}"
)

TXT_LIKE_FILES = {".txt", ".csv", ".json", ".py"}
TXT_EMBED_DESCRIPTION = (
    "You either uploaded a `{blocked_extension}` file or entered a message that was too long. "
    f"Please use our [paste bin]({PASTE_URL}) instead."
)

DISALLOWED_EMBED_DESCRIPTION = (
    "It looks like you tried to attach file type(s) that we do not allow ({joined_blacklist}). "
    "We currently allow the following file types: **{joined_whitelist}**.\n\n"
    "Feel free to ask in {meta_channel_mention} if you think this is a mistake."
)

PASTEBIN_UPLOAD_EMOJI = Emojis.check_mark
DELETE_PASTE_EMOJI = Emojis.trashcan


class ExtensionsList(FilterList[ExtensionFilter]):
    """
    A list of filters, each looking for a file attachment with a specific extension.

    If an extension is not explicitly allowed, it will be blocked.

    Whitelist defaults dictate what happens when an extension is *not* explicitly allowed,
    and whitelist filters overrides have no effect.

    Items should be added as file extensions preceded by a dot.
    """

    name = "extension"

    def __init__(self, filtering_cog: Filtering):
        super().__init__()
        filtering_cog.subscribe(self, Event.MESSAGE, Event.SNEKBOX)
        self._whitelisted_description = None

    def get_filter_type(self, content: str) -> type[Filter]:
        """Get a subclass of filter matching the filter list and the filter's content."""
        return ExtensionFilter

    @property
    def filter_types(self) -> set[type[Filter]]:
        """Return the types of filters used by this list."""
        return {ExtensionFilter}

    async def actions_for(
        self, ctx: FilterContext
    ) -> tuple[ActionSettings | None, list[str], dict[ListType, list[Filter]]]:
        """Dispatch the given event to the list's filters, and return actions to take and messages to relay to mods."""
        # Return early if the message doesn't have attachments.
        if not ctx.message or not ctx.attachments:
            return None, [], {}

        _, failed = self[ListType.ALLOW].defaults.validations.evaluate(ctx)
        if failed:  # There's no extension filtering in this context.
            return None, [], {}

        # Find all extensions in the message.
        all_ext = {
            (splitext(attachment.filename.lower())[1], attachment.filename) for attachment in ctx.attachments
        }
        new_ctx = ctx.replace(content={ext for ext, _ in all_ext})  # And prepare the context for the filters to read.
        triggered = [
            filter_ for filter_ in self[ListType.ALLOW].filters.values() if await filter_.triggered_on(new_ctx)
        ]
        allowed_ext = {filter_.content for filter_ in triggered}  # Get the extensions in the message that are allowed.

        # See if there are any extensions left which aren't allowed.
        not_allowed = {ext: filename for ext, filename in all_ext if ext not in allowed_ext}

        if ctx.event == Event.SNEKBOX:
            not_allowed = {ext: filename for ext, filename in not_allowed.items() if ext not in TXT_LIKE_FILES}

        if not not_allowed:  # Yes, it's a double negative. Meaning all attachments are allowed :)
            return None, [], {ListType.ALLOW: triggered}

        # At this point, something is disallowed.
        if ctx.event != Event.SNEKBOX:  # Don't post the embed if it's a snekbox response.
            if ".py" in not_allowed:
                # Provide a pastebin link for .py files.
                ctx.dm_embed = PY_EMBED_DESCRIPTION
            elif txt_extensions := {ext for ext in TXT_LIKE_FILES if ext in not_allowed}:
                # Work around Discord auto-conversion of messages longer than 2000 chars to .txt
                ctx.dm_embed = TXT_EMBED_DESCRIPTION.format(blocked_extension=txt_extensions.pop())
            else:
                meta_channel = bot.instance.get_channel(Channels.meta)
                if not self._whitelisted_description:
                    self._whitelisted_description = ", ".join(
                        filter_.content for filter_ in self[ListType.ALLOW].filters.values()
                    )
                ctx.dm_embed = DISALLOWED_EMBED_DESCRIPTION.format(
                    joined_whitelist=self._whitelisted_description,
                    joined_blacklist=", ".join(not_allowed),
                    meta_channel_mention=meta_channel.mention,
                )

        ctx.matches += not_allowed.values()
        ctx.blocked_exts |= set(not_allowed)
        actions = self[ListType.ALLOW].defaults.actions if ctx.event != Event.SNEKBOX else None
        return actions, [f"`{ext}`" if ext else "`No Extension`" for ext in not_allowed], {ListType.ALLOW: triggered}


class EmbedFileHandler(commands.Cog):

    def __init__(self, bot: Bot):
        self.bot = bot

    @staticmethod
    async def _convert_attachment(attachment: discord.Attachment) -> paste_service.PasteFile:
        encoding = re.search(r"charset=(\S+)", attachment.content_type).group(1)
        file_content = (await attachment.read()).decode(encoding)
        return paste_service.PasteFile(content=file_content, name=attachment.filename)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # Check if the message contains an embedded file and is not sent by a bot
        if message.author.bot or not message.attachments:
            return

        bot_reply = await message.reply(f"React with {PASTEBIN_UPLOAD_EMOJI} to upload your file to our paste bin")
        await bot_reply.add_reaction(PASTEBIN_UPLOAD_EMOJI)

        def wait_for_upload_permission(reaction: discord.Reaction, user: discord.User) -> bool:
            return (
                reaction.message.id == bot_reply.id
                and str(reaction.emoji) == PASTEBIN_UPLOAD_EMOJI
                and user == message.author
            )

        try:
            # Wait for the reaction with a timeout of 60 seconds
            await self.bot.wait_for("reaction_add", timeout=60.0, check=wait_for_upload_permission)
        except TimeoutError:
            await bot_reply.edit(content=f"~~{bot_reply.content}~~")
            await bot_reply.clear_reactions()
            return

        logging.info({f.filename: f.content_type for f in message.attachments})

        files = [
            await self._convert_attachment(f)
            for f in message.attachments
            if f.content_type.startswith("text")
        ]

        try:
            async with aiohttp.ClientSession() as session:
                paste_response = await paste_service.send_to_paste_service(files=files, http_session=session)
        except (paste_service.PasteTooLongError, ValueError):
            # paste is too long
            await bot_reply.edit(content="Your paste is too long, and couldn't be uploaded.")
            return
        except paste_service.PasteUploadError:
            await bot_reply.edit(content="There was an error uploading your paste.")
            return

        # The angle brackets around the remove link are required to stop Discord from visiting the URL to produce a
        # preview, thereby deleting the paste
        await message.author.send(content=f"[Click here](<{paste_response.removal}>) to delete your recent paste.")

        await bot_reply.edit(content=f"[Click here]({paste_response.link}) to see this code in our pastebin.")
        await bot_reply.clear_reactions()
        await bot_reply.add_reaction(DELETE_PASTE_EMOJI)

        def wait_for_delete_reaction(reaction: discord.Reaction, user: discord.User) -> bool:
            return (
                reaction.message.id == bot_reply.id
                and str(reaction.emoji) == DELETE_PASTE_EMOJI
                and user == message.author
            )

        try:
            await self.bot.wait_for("reaction_add", timeout=60.0 * 10, check=wait_for_delete_reaction)
            await paste_response.delete()
            await bot_reply.delete()
        except TimeoutError:
            pass
