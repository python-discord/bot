import logging

from .bigbrother import BigBrother


log = logging.getLogger(__name__)


def setup(bot):
    log.trace("Started adding BigBrother cog")
    bot.add_cog(BigBrother(bot))
    log.trace("Finished adding BigBrother cog")
