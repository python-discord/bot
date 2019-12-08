import logging

from bot.bot import Bot
from .cog import Sync

log = logging.getLogger(__name__)


def setup(bot: Bot) -> None:
    """Sync cog load."""
    bot.add_cog(Sync(bot))
    log.info("Cog loaded: Sync")
