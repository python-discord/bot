import logging

from discord.ext.commands import Cog

from bot.bot import Bot

log = logging.getLogger(__name__)


class Incidents(Cog):
    """Automation for the #incidents channel."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
