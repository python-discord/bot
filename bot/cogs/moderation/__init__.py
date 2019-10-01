import logging

from discord.ext.commands import Bot

from . import utils
from .infractions import Infractions
from .management import ModManagement
from .modlog import ModLog
from .superstarify import Superstarify

__all__ = ("utils", "Infractions", "ModManagement", "ModLog", "Superstarify")

log = logging.getLogger(__name__)


def setup(bot: Bot) -> None:
    """Load the moderation extension (Infractions, ModManagement, ModLog, & Superstarify cogs)."""
    bot.add_cog(Infractions(bot))
    log.info("Cog loaded: Infractions")

    bot.add_cog(ModLog(bot))
    log.info("Cog loaded: ModLog")

    bot.add_cog(ModManagement(bot))
    log.info("Cog loaded: ModManagement")

    bot.add_cog(Superstarify(bot))
    log.info("Cog loaded: Superstarify")
