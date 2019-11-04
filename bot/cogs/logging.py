import logging

from discord import Embed
from discord.ext.commands import Bot, Cog

from bot.constants import Channels, DEBUG_MODE


log = logging.getLogger(__name__)


class Logging(Cog):
    """Debug logging module."""

    def __init__(self, bot: Bot):
        self.bot = bot

        self.bot.loop.create_task(self.startup_greeting())

    async def startup_greeting(self) -> None:
        """Announce our presence to the configured devlog channel."""
        await self.bot.wait_until_ready()
        log.info("Bot connected!")

        embed = Embed(description="Connected!")
        embed.set_author(
            name="Python Bot",
            url="https://github.com/python-discord/bot",
            icon_url=(
                "https://raw.githubusercontent.com/"
                "python-discord/branding/master/logos/logo_circle/logo_circle_large.png"
            )
        )

        if not DEBUG_MODE:
            await self.bot.get_channel(Channels.devlog).send(embed=embed)


def setup(bot: Bot) -> None:
    """Logging cog load."""
    bot.add_cog(Logging(bot))
    log.info("Cog loaded: Logging")
