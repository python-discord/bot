import logging

from discord import Embed
from discord.ext.commands import Bot

from bot.constants import Channels, DEBUG_MODE


log = logging.getLogger(__name__)


class Logging:
    """Debug logging module."""

    def __init__(self, bot: Bot):
        self.bot = bot

    async def on_ready(self) -> None:
        """Announce our presence to the configured devlog channel."""
        log.info("Bot connected!")

        embed = Embed(description="Connected!")
        embed.set_author(
            name="Python Bot",
            url="https://github.com/python-discord/bot",
            icon_url="https://github.com/python-discord/branding/blob/master/logos/logo_circle/logo_circle_256.png"
        )

        if not DEBUG_MODE:
            await self.bot.get_channel(Channels.devlog).send(embed=embed)


def setup(bot: Bot) -> None:
    """Logging cog load."""
    bot.add_cog(Logging(bot))
    log.info("Cog loaded: Logging")
