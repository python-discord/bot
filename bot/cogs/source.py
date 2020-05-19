from discord.ext.commands import Cog

from bot.bot import Bot


class Source(Cog):
    """Cog of Python Discord project source information."""

    def __init__(self, bot: Bot):
        self.bot = bot


def setup(bot: Bot) -> None:
    """Load `Source` cog."""
    bot.add_cog(Source(bot))
