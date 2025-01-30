from __future__ import annotations

import re

import aiohttp
import discord
from discord.ext import commands
from pydis_core.utils import paste_service

from bot.bot import Bot
from bot.constants import Emojis
from bot.log import get_logger

log = get_logger(__name__)

PASTEBIN_UPLOAD_EMOJI = Emojis.check_mark
DELETE_PASTE_EMOJI = Emojis.trashcan


class EmbedFileHandler(commands.Cog):
    """
    Handles automatic uploading of attachments to the paste bin.

    Whenever a user uploads one or more attachments that is text-based (py, txt, csv, etc.), this cog offers to upload
    all the attachments to the paste bin automatically. The steps are as follows:
    - The bot replies to the message containing the attachments, asking the user to react with a checkmark to consent
        to having the content uploaded.
    - If consent is given, the bot uploads the contents and edits its own message to contain the link.
    - The bot DMs the user the delete link for the paste.
    - The bot waits for the user to react with a trashcan emoji, in which case the bot deletes the paste and its own
        message.
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self.pending_messages = set[int]()

    @staticmethod
    async def _convert_attachment(attachment: discord.Attachment) -> paste_service.PasteFile:
        """Converts an attachment to a PasteFile, according to the attachment's file encoding."""
        encoding = re.search(r"charset=(\S+)", attachment.content_type).group(1)
        file_content = (await attachment.read()).decode(encoding)
        return paste_service.PasteFile(content=file_content, name=attachment.filename)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        """Allows us to know which messages with attachments have been deleted."""
        self.pending_messages.discard(message.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Listens for messages containing attachments and offers to upload them to the pastebin."""
        # Check if the message contains an embedded file and is not sent by a bot.
        if message.author.bot or not any(a.content_type.startswith("text") for a in message.attachments):
            return

        log.trace(f"Offering to upload attachments for {message.author} in {message.channel}, message {message.id}")
        self.pending_messages.add(message.id)

        # Offer to upload the attachments and wait for the user's reaction.
        bot_reply = await message.reply(
            f"Please react with {PASTEBIN_UPLOAD_EMOJI} to upload your file(s) to our "
            f"[paste bin](<https://paste.pythondiscord.com/>), which is more accessible for some users."
        )
        await bot_reply.add_reaction(PASTEBIN_UPLOAD_EMOJI)

        def wait_for_upload_permission(reaction: discord.Reaction, user: discord.User) -> bool:
            return (
                reaction.message.id == bot_reply.id
                and str(reaction.emoji) == PASTEBIN_UPLOAD_EMOJI
                and user == message.author
            )

        try:
            # Wait for the reaction with a timeout of 60 seconds.
            await self.bot.wait_for("reaction_add", timeout=60.0, check=wait_for_upload_permission)
        except TimeoutError:
            # The user does not grant permission before the timeout. Exit early.
            log.trace(f"{message.author} didn't give permission to upload {message.id} content; aborting.")
            await bot_reply.edit(content=f"~~{bot_reply.content}~~")
            await bot_reply.clear_reactions()

        if message.id not in self.pending_messages:
            log.trace(f"{message.author}'s message was deleted before the attachments could be uploaded; aborting.")
            await bot_reply.delete()
            return

        # In either case, we do not want the message ID in pending_messages anymore.
        self.pending_messages.discard(message.id)

        # Extract the attachments.
        files = [
            await self._convert_attachment(f)
            for f in message.attachments
            if "charset" in f.content_type
        ]

        # Upload the files to the paste bin, exiting early if there's an error.
        log.trace(f"Attempting to upload {len(files)} file(s) to pastebin.")
        try:
            async with aiohttp.ClientSession() as session:
                paste_response = await paste_service.send_to_paste_service(files=files, http_session=session)
        except (paste_service.PasteTooLongError, ValueError):
            log.trace(f"{message.author}'s attachments were too long.")
            await bot_reply.edit(content="Your paste is too long, and couldn't be uploaded.")
            return
        except paste_service.PasteUploadError:
            log.trace(f"Unexpected error uploading {message.author}'s attachments.")
            await bot_reply.edit(content="There was an error uploading your paste.")
            return

        # Send the user a DM with the delete link for the paste.
        # The angle brackets around the remove link are required to stop Discord from visiting the URL to produce a
        # preview, thereby deleting the paste
        await message.author.send(content=f"[Click here](<{paste_response.removal}>) to delete your recent paste.")

        # Edit the bot message to contain the link to the paste.
        await bot_reply.edit(content=f"[Click here]({paste_response.link}) to see this code in our pastebin.")
        await bot_reply.clear_reactions()
        await bot_reply.add_reaction(DELETE_PASTE_EMOJI)

        # Wait for the user to react with a trash can, which they can use to delete the paste.

        def wait_for_delete_reaction(reaction: discord.Reaction, user: discord.User) -> bool:
            return (
                reaction.message.id == bot_reply.id
                and str(reaction.emoji) == DELETE_PASTE_EMOJI
                and user == message.author
            )

        try:
            log.trace(f"Offering to delete {message.author}'s attachments in {message.channel}, message {message.id}")
            await self.bot.wait_for("reaction_add", timeout=60.0 * 10, check=wait_for_delete_reaction)
            # Delete the paste by visiting the removal URL.
            async with aiohttp.ClientSession() as session:
                await session.get(paste_response.removal)
            await bot_reply.delete()
        except TimeoutError:
            log.trace(f"Offer to delete {message.author}'s attachments timed out.")


async def setup(bot: Bot) -> None:
    """Load the EmbedFileHandler cog."""
    await bot.add_cog(EmbedFileHandler(bot))
