import logging
import time
from typing import Optional

import discord
from discord import Message, RawMessageUpdateEvent
from discord.ext.commands import Bot, Cog

from bot.cogs.token_remover import TokenRemover
from bot.constants import Channels, DEBUG_MODE
from bot.utils import has_lines
from bot.utils.channel import is_help_channel
from bot.utils.messages import wait_for_deletion
from .instructions import get_instructions

log = logging.getLogger(__name__)


class CodeBlockCog(Cog, name="Code Block"):
    """
    Detect improperly formatted Markdown code blocks and suggest proper formatting.

    There are four basic ways in which a code block is considered improperly formatted:

    1. The code is not within a code block at all
        * Ignored if the code is not valid Python or Python REPL code
    2. Incorrect characters are used for backticks
    3. A language for syntax highlighting is not specified
        * Ignored if the code is not valid Python or Python REPL code
    4. A syntax highlighting language is incorrectly specified
        * Ignored if the language specified doesn't look like it was meant for Python
        * This can go wrong in two ways:
            1. Spaces before the language
            2. No newline immediately following the language

    Messages with 3 or fewer lines overall are ignored. Each code block is subject to this threshold
    as well i.e. the text between the ticks must be greater than 3 lines. Detecting multiple code
    blocks is supported. However, if at least one code block is correct, then instructions will not
    be sent even if others are incorrect. When multiple incorrect code blocks are found, only the
    first one is used as the basis for the instructions sent.

    When an issue is detected, an embed is sent containing specific instructions on fixing what
    is wrong. If the user edits their message to fix the code block, the instructions will be
    removed. If they fail to fix the code block with an edit, the instructions will be updated to
    show what is still incorrect after the user's edit. The embed can be manually deleted with a
    reaction. Otherwise, it will automatically be removed after 5 minutes.

    The cog only detects messages in whitelisted channels. Channels may also have a 300-second
    cooldown on the instructions being sent. See `__init__` for which channels are whitelisted or
    have cooldowns enabled. Note that all help channels are also whitelisted with cooldowns enabled.
    """

    def __init__(self, bot: Bot):
        self.bot = bot

        # Stores allowed channels plus epoch times since the last instructional messages sent.
        self.channel_cooldowns = {
            Channels.python_discussion: 0,
        }

        # These channels will also work, but will not be subject to a cooldown.
        self.channel_whitelist = (
            Channels.bot_commands,
        )

        # Maps users' messages to the messages the bot sent with instructions.
        self.codeblock_message_ids = {}

    @staticmethod
    def create_embed(instructions: str) -> discord.Embed:
        """Return an embed which displays code block formatting `instructions`."""
        return discord.Embed(description=instructions)

    async def get_sent_instructions(self, payload: RawMessageUpdateEvent) -> Optional[Message]:
        """
        Return the bot's sent instructions message associated with a user's message `payload`.

        Return None if the message cannot be found. In this case, it's likely the message was
        deleted either manually via a reaction or automatically by a timer.
        """
        log.trace(f"Retrieving instructions message for ID {payload.message_id}")
        channel = self.bot.get_channel(int(payload.data.get("channel_id")))

        try:
            return await channel.fetch_message(self.codeblock_message_ids[payload.message_id])
        except discord.NotFound:
            log.debug("Could not find instructions message; it was probably deleted.")
            return None

    def is_on_cooldown(self, channel: discord.TextChannel) -> bool:
        """
        Return True if an embed was sent for `channel` in the last 300 seconds.

        Note: only channels in the `channel_cooldowns` have cooldowns enabled.
        """
        log.trace(f"Checking if #{channel} is on cooldown.")
        return (time.time() - self.channel_cooldowns.get(channel.id, 0)) < 300

    def is_valid_channel(self, channel: discord.TextChannel) -> bool:
        """Return True if `channel` is a help channel, may be on a cooldown, or is whitelisted."""
        log.trace(f"Checking if #{channel} qualifies for code block detection.")
        return (
            is_help_channel(channel)
            or channel.id in self.channel_cooldowns
            or channel.id in self.channel_whitelist
        )

    async def send_instructions(self, message: discord.Message, instructions: str) -> None:
        """
        Send an embed with `instructions` on fixing an incorrect code block in a `message`.

        The embed will be deleted automatically after 5 minutes.
        """
        log.info(f"Sending code block formatting instructions for message {message.id}.")

        embed = self.create_embed(instructions)
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
            and has_lines(message.content, 4)
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
            await self.send_instructions(msg, instructions)

            if msg.channel.id not in self.channel_whitelist:
                log.debug(f"Adding #{msg.channel} to the channel cooldowns.")
                self.channel_cooldowns[msg.channel.id] = time.time()

    @Cog.listener()
    async def on_raw_message_edit(self, payload: RawMessageUpdateEvent) -> None:
        """Delete the instructional message if an edited message had its code blocks fixed."""
        if payload.message_id not in self.codeblock_message_ids:
            log.trace(f"Ignoring message edit {payload.message_id}: message isn't being tracked.")
            return

        if payload.data.get("content") is None or payload.data.get("channel_id") is None:
            log.trace(f"Ignoring message edit {payload.message_id}: missing content or channel ID.")
            return

        # Parse the message to see if the code blocks have been fixed.
        content = payload.data.get("content")
        instructions = get_instructions(content)

        bot_message = await self.get_sent_instructions(payload)
        if not bot_message:
            return

        if not instructions:
            log.info("User's incorrect code block has been fixed. Removing instructions message.")
            await bot_message.delete()
            del self.codeblock_message_ids[payload.message_id]
        else:
            log.info("Message edited but still has invalid code blocks; editing the instructions.")
            await bot_message.edit(embed=self.create_embed(instructions))
