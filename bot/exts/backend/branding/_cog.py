import logging

from discord.ext import commands

from bot.bot import Bot
from bot.exts.backend.branding._repository import BrandingRepository

log = logging.getLogger(__name__)


class Branding(commands.Cog):
    """Guild branding management."""

    def __init__(self, bot: Bot) -> None:
        """Instantiate repository abstraction."""
        self.bot = bot
        self.repository = BrandingRepository(bot)
