from discord import Embed
from discord.ext.commands import Cog
from pydis_core.utils import scheduling

from bot.bot import Bot
from bot.constants import Channels, DEBUG_MODE
from bot.log import get_logger

log = get_logger(__name__)


class Logging(Cog):
    """Debug logging module."""

    def __init__(self, bot: Bot):
        self.bot = bot

        scheduling.create_task(self.startup_greeting())

    async def startup_greeting(self) -> None:
        """Announce our presence to the configured devlog channel."""
        await self.bot.wait_until_guild_available()
        log.info("Bot connected!")

        embed = Embed(description="Connected!")
        embed.set_author(
            name="Python Bot",
            url="https://github.com/python-discord/bot",
            icon_url=(
                "https://raw.githubusercontent.com/"
                "python-discord/branding/main/logos/logo_circle/logo_circle_large.png"
            )
        )

        if not DEBUG_MODE:
            await self.bot.get_channel(Channels.dev_log).send(embed=embed)


async def setup(bot: Bot) -> None:
    """Load the Logging cog."""
    await bot.add_cog(Logging(bot))
