import logging
import time

import discord
from discord import Embed, Message, RawMessageUpdateEvent
from discord.ext.commands import Bot, Cog

from bot.cogs.token_remover import TokenRemover
from bot.constants import Categories, Channels, DEBUG_MODE
from bot.utils.messages import wait_for_deletion
from . import instructions, parsing

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
        return (
            getattr(channel, "category", None)
            and channel.category.id in (Categories.help_available, Categories.help_in_use)
        )

    def is_on_cooldown(self, channel: discord.TextChannel) -> bool:
        """
        Return True if an embed was sent for `channel` in the last 300 seconds.

        Note: only channels in the `channel_cooldowns` have cooldowns enabled.
        """
        return (time.time() - self.channel_cooldowns.get(channel.id, 0)) < 300

    def is_valid_channel(self, channel: discord.TextChannel) -> bool:
        """Return True if `channel` is a help channel, may be on cooldown, or is whitelisted."""
        return (
            self.is_help_channel(channel)
            or channel.id in self.channel_cooldowns
            or channel.id in self.channel_whitelist
        )

    async def send_guide_embed(self, message: discord.Message, description: str) -> None:
        """
        Send an embed with `description` as a guide for an improperly formatted `message`.

        The embed will be deleted automatically after 5 minutes.
        """
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
            return

        # When debugging, ignore cooldowns.
        if self.is_on_cooldown(msg.channel) and not DEBUG_MODE:
            return

        blocks = parsing.find_code_blocks(msg.content)
        if not blocks:
            # No code blocks found in the message.
            description = instructions.get_no_ticks_message(msg.content)
        else:
            # Get the first code block with invalid ticks.
            block = next((block for block in blocks if block.tick != parsing.BACKTICK), None)

            if block:
                # A code block exists but has invalid ticks.
                description = instructions.get_bad_ticks_message(block)
            else:
                # Only other possibility is a block with valid ticks but a missing language.
                block = blocks[0]

                # Check for a bad language first to avoid parsing content into an AST.
                description = instructions.get_bad_lang_message(block.content)
                if not description:
                    description = instructions.get_no_lang_message(block.content)

        if description:
            await self.send_guide_embed(msg, description)
            if msg.channel.id not in self.channel_whitelist:
                self.channel_cooldowns[msg.channel.id] = time.time()

    @Cog.listener()
    async def on_raw_message_edit(self, payload: RawMessageUpdateEvent) -> None:
        """Check to see if an edited message (previously called out) still contains poorly formatted code."""
        if (
            # Checks to see if the message was called out by the bot
            payload.message_id not in self.codeblock_message_ids
            # Makes sure that there is content in the message
            or payload.data.get("content") is None
            # Makes sure there's a channel id in the message payload
            or payload.data.get("channel_id") is None
        ):
            return

        # Retrieve channel and message objects for use later
        channel = self.bot.get_channel(int(payload.data.get("channel_id")))
        user_message = await channel.fetch_message(payload.message_id)

        #  Checks to see if the user has corrected their codeblock.  If it's fixed, has_fixed_codeblock will be None
        has_fixed_codeblock = self.codeblock_stripping(payload.data.get("content"), parsing.has_bad_ticks(user_message))

        # If the message is fixed, delete the bot message and the entry from the id dictionary
        if has_fixed_codeblock is None:
            bot_message = await channel.fetch_message(self.codeblock_message_ids[payload.message_id])
            await bot_message.delete()
            del self.codeblock_message_ids[payload.message_id]
            log.trace("User's incorrect code block has been fixed. Removing bot formatting message.")
