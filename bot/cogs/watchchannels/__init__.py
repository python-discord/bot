import logging

from bot.bot import Bot
from .bigbrother import BigBrother
from .talentpool import TalentPool


log = logging.getLogger(__name__)


def setup(bot: Bot) -> None:
    """Monitoring cogs load."""
    bot.add_cog(BigBrother(bot))
    log.info("Cog loaded: BigBrother")

    bot.add_cog(TalentPool(bot))
    log.info("Cog loaded: TalentPool")
