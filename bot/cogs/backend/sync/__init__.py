from bot.bot import Bot
from ._cog import Sync


def setup(bot: Bot) -> None:
    """Load the Sync cog."""
    bot.add_cog(Sync(bot))
