import logging
import time

import discord
from discord import Embed, Message, RawMessageUpdateEvent
from discord.ext.commands import Bot, Cog

from bot.cogs.token_remover import TokenRemover
from bot.constants import Categories, Channels, DEBUG_MODE
from bot.utils.messages import wait_for_deletion
from . import parsing
from .instructions import get_instructions

log = logging.getLogger(__name__)


class CodeBlockCog(Cog, name="Code Block"):
    """Detect improperly formatted code blocks and suggest proper formatting."""

    def __init__(self, bot: Bot):
        self.bot = bot

        # Stores allowed channels plus epoch time since last call.
        self.channel_cooldowns = {
            Channels.python_discussion: 0,
        }

        # These channels will also work, but will not be subject to cooldown
        self.channel_whitelist = (
            Channels.bot_commands,
        )

        # Stores improperly formatted Python codeblock message ids and the corresponding bot message
        self.codeblock_message_ids = {}

    @staticmethod
    def is_help_channel(channel: discord.TextChannel) -> bool:
        """Return True if `channel` is in one of the help categories."""
        log.trace(f"Checking if #{channel} is a help channel.")
        return (
            getattr(channel, "category", None)
            and channel.category.id in (Categories.help_available, Categories.help_in_use)
        )

    def is_on_cooldown(self, channel: discord.TextChannel) -> bool:
        """
        Return True if an embed was sent for `channel` in the last 300 seconds.

        Note: only channels in the `channel_cooldowns` have cooldowns enabled.
        """
        log.trace(f"Checking if #{channel} is on cooldown.")
        return (time.time() - self.channel_cooldowns.get(channel.id, 0)) < 300

    def is_valid_channel(self, channel: discord.TextChannel) -> bool:
        """Return True if `channel` is a help channel, may be on cooldown, or is whitelisted."""
        log.trace(f"Checking if #{channel} qualifies for code block detection.")
        return (
            self.is_help_channel(channel)
            or channel.id in self.channel_cooldowns
            or channel.id in self.channel_whitelist
        )

    async def remove_instructions(self, payload: RawMessageUpdateEvent) -> None:
        """
        Remove the code block instructions message.

        `payload` is the data for the message edit event performed by a user which resulted in their
        code blocks being corrected.
        """
        log.trace("User's incorrect code block has been fixed. Removing instructions message.")

        channel = self.bot.get_channel(int(payload.data.get("channel_id")))
        bot_message = await channel.fetch_message(self.codeblock_message_ids[payload.message_id])

        await bot_message.delete()
        del self.codeblock_message_ids[payload.message_id]

    async def send_guide_embed(self, message: discord.Message, description: str) -> None:
        """
        Send an embed with `description` as a guide for an improperly formatted `message`.

        The embed will be deleted automatically after 5 minutes.
        """
        log.trace("Sending an embed with code block formatting instructions.")

        embed = Embed(description=description)
        bot_message = await message.channel.send(f"Hey {message.author.mention}!", embed=embed)
        self.codeblock_message_ids[message.id] = bot_message.id

        self.bot.loop.create_task(
            wait_for_deletion(bot_message, user_ids=(message.author.id,), client=self.bot)
        )

    def should_parse(self, message: discord.Message) -> bool:
        """
        Return True if `message` should be parsed.

        A qualifying message:

        1. Is not authored by a bot
        2. Is in a valid channel
        3. Has more than 3 lines
        4. Has no bot token
        """
        return (
            not message.author.bot
            and self.is_valid_channel(message.channel)
            and len(message.content.split("\n", 3)) > 3
            and not TokenRemover.find_token_in_message(message)
        )

    @Cog.listener()
    async def on_message(self, msg: Message) -> None:
        """Detect incorrect Markdown code blocks in `msg` and send instructions to fix them."""
        if not self.should_parse(msg):
            log.trace(f"Skipping code block detection of {msg.id}: message doesn't qualify.")
            return

        # When debugging, ignore cooldowns.
        if self.is_on_cooldown(msg.channel) and not DEBUG_MODE:
            log.trace(f"Skipping code block detection of {msg.id}: #{msg.channel} is on cooldown.")
            return

        instructions = get_instructions(msg.content)
        if instructions:
            await self.send_guide_embed(msg, instructions)

            if msg.channel.id not in self.channel_whitelist:
                log.trace(f"Adding #{msg.channel} to the channel cooldowns.")
                self.channel_cooldowns[msg.channel.id] = time.time()

    @Cog.listener()
    async def on_raw_message_edit(self, payload: RawMessageUpdateEvent) -> None:
        """Delete the instructions message if an edited message had its code blocks fixed."""
        if (
            # Checks to see if the message was called out by the bot
            payload.message_id not in self.codeblock_message_ids
            # Makes sure that there is content in the message
            or payload.data.get("content") is None
            # Makes sure there's a channel id in the message payload
            or payload.data.get("channel_id") is None
        ):
            log.trace("Message edit does not qualify for code block detection.")
            return

        # Parse the message to see if the code blocks have been fixed.
        code_blocks = parsing.find_code_blocks(payload.data.get("content"))

        # If the message is fixed, delete the bot message and the entry from the id dictionary.
        if not code_blocks:
            await self.remove_instructions(payload)
