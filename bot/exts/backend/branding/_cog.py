import logging

from discord.ext import commands

from bot.bot import Bot

log = logging.getLogger(__name__)


class Branding(commands.Cog):
    """Guild branding management."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
