from discord.ext.commands import Cog

from bot.bot import Bot


class News(Cog):
    """Post new PEPs and Python News to `#python-news`."""

    def __init__(self, bot: Bot):
        self.bot = bot


def setup(bot: Bot) -> None:
    """Add `News` cog."""
    bot.add_cog(News(bot))
