import logging

import discord
from discord import Color
from discord.ext.commands import Cog

from bot import constants
from bot.bot import Bot
from bot.utils.messages import send_attachments
from bot.utils.webhooks import send_webhook

log = logging.getLogger(__name__)


class DMRelay(Cog):
    """Debug logging module."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.webhook_id = constants.Webhooks.dm_log
        self.webhook = None
        self.bot.loop.create_task(self.fetch_webhook())

    async def fetch_webhook(self) -> None:
        """Fetches the webhook object, so we can post to it."""
        await self.bot.wait_until_guild_available()

        try:
            self.webhook = await self.bot.fetch_webhook(self.webhook_id)
        except discord.HTTPException:
            log.exception(f"Failed to fetch webhook with id `{self.webhook_id}`")

    @Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Relays the message's content and attachments to the dm_log channel."""
        # Only relay DMs from humans
        if message.author.bot or message.guild:
            return

        clean_content = message.clean_content
        if clean_content:
            await send_webhook(
                webhook=self.webhook,
                content=message.clean_content,
                username=message.author.display_name,
                avatar_url=message.author.avatar_url
            )

        # Handle any attachments
        if message.attachments:
            try:
                await send_attachments(message, self.webhook)
            except (discord.errors.Forbidden, discord.errors.NotFound):
                e = discord.Embed(
                    description=":x: **This message contained an attachment, but it could not be retrieved**",
                    color=Color.red()
                )
                await send_webhook(
                    webhook=self.webhook,
                    embed=e,
                    username=message.author.display_name,
                    avatar_url=message.author.avatar_url
                )
            except discord.HTTPException:
                log.exception("Failed to send an attachment to the webhook")


def setup(bot: Bot) -> None:
    """Load the DMRelay  cog."""
    bot.add_cog(DMRelay(bot))
