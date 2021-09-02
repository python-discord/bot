import logging

from discord.ext import commands

from bot.bot import Bot

log = logging.getLogger(__name__)


class Patreon(commands.Cog):
    """Cog that shows patreon supporters."""

    def __init__(self, bot: Bot):
        self.bot = bot


def setup(bot: Bot) -> None:
    """Load the patreon cog."""
    bot.add_cog(Patreon(bot))
