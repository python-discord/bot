import logging

from discord import Embed
from discord.ext.commands import Bot, Cog

from bot.constants import Channels, DEBUG_MODE


log = logging.getLogger(__name__)


class Logging(Cog):
    """
    Debug logging module
    """

    def __init__(self, bot: Bot):
        self.bot = bot

    @Cog.listener()
    async def on_ready(self):
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


def setup(bot):
    bot.add_cog(Logging(bot))
    log.info("Cog loaded: Logging")
