import logging

from .cog import Sync

log = logging.getLogger(__name__)


def setup(bot):
    bot.add_cog(Sync(bot))
    log.info("Cog loaded: Sync")
