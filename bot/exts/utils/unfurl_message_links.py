import discord
from discord.ext.commands import Cog

from bot.bot import Bot
from bot.constants import Guild
from bot.utils.channel import is_staff_channel
from bot.utils.messages import extract_message_links, make_message_link_embed


class UnfurlMsgLinks(Cog):
    """Unfurl message links and send embeds containing information about the linked message."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Unfurl messages linked in the message if any and send the message link embed."""
        if (
            not message.guild
            or message.guild.id != Guild.id
            or not is_staff_channel(message.channel)
        ):
            return

        if message_links := await extract_message_links(message):
            ctx = await self.bot.get_context(message)
            embeds = [await make_message_link_embed(ctx, msg) for msg in message_links]
            await message.reply(embeds=[embed for embed in embeds if embed])


def setup(bot: Bot) -> None:
    """Load the UnfurlMsgLinks cog."""
    bot.add_cog(UnfurlMsgLinks(bot))
