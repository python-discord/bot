from bot.bot import Bot
from ._cog import DocCog

MAX_SIGNATURE_AMOUNT = 3
PRIORITY_PACKAGES = (
    "python",
)


def setup(bot: Bot) -> None:
    """Load the Doc cog."""
    bot.add_cog(DocCog(bot))
