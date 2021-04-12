import logging

import discord
from discord.ext.commands import Cog, Context, command, has_any_role

from bot.bot import Bot
from bot.constants import Emojis, MODERATION_ROLES
from bot.utils.services import send_to_paste_service

log = logging.getLogger(__name__)


class DMRelay(Cog):
    """Inspect messages sent to the bot."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @command(aliases=("relay", "dr"))
    async def dmrelay(self, ctx: Context, user: discord.User, limit: int = 100) -> None:
        """Relays the direct message history between the bot and given user."""
        log.trace(f"Relaying DMs with {user.name} ({user.id})")

        if user.bot:
            await ctx.send(f"{Emojis.cross_mark} No direct message history with bots.")
            return

        output = ""
        async for msg in user.history(limit=limit, oldest_first=True):
            created_at = msg.created_at.strftime(r"%Y-%m-%d %H:%M")

            # Metadata (author, created_at, id)
            output += f"{msg.author} [{created_at}] ({msg.id}): "

            # Content
            if msg.content:
                output += msg.content + "\n"

            # Embeds
            if (embeds := len(msg.embeds)) > 0:
                output += f"<{embeds} embed{'s' if embeds > 1 else ''}>\n"

            # Attachments
            attachments = "\n".join(a.url for a in msg.attachments)
            if attachments:
                output += attachments + "\n"

        if not output:
            await ctx.send(f"{Emojis.cross_mark} No direct message history with {user.mention}.")
            return

        metadata = (
            f"User: {user} ({user.id})\n"
            f"Channel ID: {user.dm_channel.id}\n\n"
        )

        paste_link = await send_to_paste_service(metadata + output, extension="txt")

        if paste_link is None:
            await ctx.send(f"{Emojis.cross_mark} Failed to upload output to hastebin.")
            return

        await ctx.send(paste_link)

    async def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators to invoke the commands in this cog."""
        return await has_any_role(*MODERATION_ROLES).predicate(ctx)


def setup(bot: Bot) -> None:
    """Load the DMRelay cog."""
    bot.add_cog(DMRelay(bot))
