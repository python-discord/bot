from bot.bot import Bot
from .cog import CodeBlockCog


def setup(bot: Bot) -> None:
    """Load the CodeBlockCog cog."""
    bot.add_cog(CodeBlockCog(bot))
