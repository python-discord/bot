import logging

from discord.ext.commands import Bot

from .infractions import Infractions
from .management import ModManagement
from .modlog import ModLog

log = logging.getLogger(__name__)


def setup(bot: Bot) -> None:
    """Load the moderation extension with the Infractions, ModManagement, and ModLog cogs."""
    bot.add_cog(Infractions(bot))
    log.info("Cog loaded: Infractions")

    bot.add_cog(ModLog(bot))
    log.info("Cog loaded: ModLog")

    bot.add_cog(ModManagement(bot))
    log.info("Cog loaded: ModManagement")
