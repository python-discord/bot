from bot.bot import Bot
from .bigbrother import BigBrother
from .talentpool import TalentPool


def setup(bot: Bot) -> None:
    """Load the BigBrother and TalentPool cogs."""
    bot.add_cog(BigBrother(bot))
    bot.add_cog(TalentPool(bot))
