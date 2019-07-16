import logging

from .bigbrother import BigBrother
from .talentpool import TalentPool


log = logging.getLogger(__name__)


def setup(bot):
    bot.add_cog(BigBrother(bot))
    log.info("Cog loaded: BigBrother")

    bot.add_cog(TalentPool(bot))
    log.info("Cog loaded: TalentPool")
