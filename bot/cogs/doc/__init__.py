from bot.bot import Bot
from .cog import DocCog


def setup(bot: Bot) -> None:
    """Load the Doc cog."""
    bot.add_cog(DocCog(bot))
