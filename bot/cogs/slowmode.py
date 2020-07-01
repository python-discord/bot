from discord.ext.commands import Cog

from bot.bot import Bot


class Slowmode(Cog):

    def __init__(self, bot: Bot) -> None:
        self.bot = bot


def setup(bot: Bot) -> None:
    """Load the Slowmode cog."""
    bot.add_cog(Slowmode(bot))
