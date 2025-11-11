import re

import discord
from discord.ext import commands
from pydis_core.utils import paste_service

from bot.bot import Bot
from bot.constants import Emojis
from bot.log import get_logger

log = get_logger(__name__)

UPLOAD_EMOJI = Emojis.check_mark
DELETE_EMOJI = Emojis.trashcan


class AutoTextAttachmentUploader(commands.Cog):
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
        file_content_bytes = await attachment.read()
        file_content = file_content_bytes.decode(encoding)
        return paste_service.PasteFile(content=file_content, name=attachment.filename)

    async def wait_for_user_reaction(
        self,
        message: discord.Message,
        user: discord.User,
        emoji: str,
        timeout: float = 60,
    ) -> bool:
        """Wait for `timeout` seconds for `user` to react to `message` with `emoji`."""
        def wait_for_reaction(reaction: discord.Reaction, reactor: discord.User) -> bool:
            return (
                reaction.message.id == message.id
                and str(reaction.emoji) == emoji
                and reactor == user
            )

        await message.add_reaction(emoji)
        log.trace(f"Waiting for {user.name} to react to {message.id} with {emoji}")

        try:
            await self.bot.wait_for("reaction_add", timeout=timeout, check=wait_for_reaction)
        except TimeoutError:
            log.trace(f"User {user.name} did not react to message {message.id} with {emoji}")
            await message.clear_reactions()
            return False

        return True

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        """Allows us to know which messages with attachments have been deleted."""
        self.pending_messages.discard(message.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Listens for messages containing attachments and offers to upload them to the pastebin."""
        # Check the message is not sent by a bot or in DMs.
        if message.author.bot or not message.guild:
            return

        # Check if the message contains any text-based attachments.
        # we only require a charset here, as its setting is matched
        attachments: list[discord.Attachment] = []
        for attachment in message.attachments:
            if (
                attachment.content_type
                and "charset" in attachment.content_type
            ):
                attachments.append(attachment)

        if not attachments:
            return

        log.trace(f"Offering to upload attachments for {message.author} in {message.channel}, message {message.id}")
        self.pending_messages.add(message.id)

        # Offer to upload the attachments and wait for the user's reaction.
        bot_reply = await message.reply(
            f"Please react with {UPLOAD_EMOJI} to upload your file(s) to our "
            f"[paste bin](<https://paste.pythondiscord.com/>), which is more accessible for some users."
        )

        permission_granted = await self.wait_for_user_reaction(bot_reply, message.author, UPLOAD_EMOJI, 60. * 3)

        if not permission_granted:
            log.trace(f"{message.author} didn't give permission to upload {message.id} content; aborting.")
            await bot_reply.edit(content=f"~~{bot_reply.content}~~")
            return

        if message.id not in self.pending_messages:
            log.trace(f"{message.author}'s message was deleted before the attachments could be uploaded; aborting.")
            await bot_reply.delete()
            return

        # In either case, we do not want the message ID in pending_messages anymore.
        self.pending_messages.discard(message.id)

        # Extract the attachments.
        files = [await self._convert_attachment(f) for f in attachments]

        # Upload the files to the paste bin, exiting early if there's an error.
        log.trace(f"Attempting to upload {len(files)} file(s) to pastebin.")
        try:
            paste_response = await paste_service.send_to_paste_service(files=files, http_session=self.bot.http_session)
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
        try:
            await message.author.send(
                f"[Click here](<{paste_response.removal}>) to delete the pasted attachment"
                f" contents copied from [your message](<{message.jump_url}>)"
            )
        except discord.Forbidden:
            log.debug(f"User {message.author} has DMs disabled, skipping delete link DM.")

        # Edit the bot message to contain the link to the paste.
        await bot_reply.edit(content=f"[Click here]({paste_response.link}) to see this code in our pastebin.")
        await bot_reply.clear_reactions()
        await bot_reply.add_reaction(DELETE_EMOJI)

        # Wait for the user to react with a trash can, which they can use to delete the paste.
        log.trace(f"Offering to delete {message.author}'s attachments in {message.channel}, message {message.id}")
        user_wants_delete = await self.wait_for_user_reaction(bot_reply, message.author, DELETE_EMOJI, 60. * 10)

        if not user_wants_delete:
            return

        # Delete the paste and the bot's message.
        await self.bot.http_session.get(paste_response.removal)

        await bot_reply.delete()


async def setup(bot: Bot) -> None:
    """Load the EmbedFileHandler cog."""
    await bot.add_cog(AutoTextAttachmentUploader(bot))
