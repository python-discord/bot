from bot.bot import Bot

MAX_SIGNATURE_AMOUNT = 3
PRIORITY_PACKAGES = (
    "python",
)


def setup(bot: Bot) -> None:
    """Load the Doc cog."""
    from ._cog import DocCog
    bot.add_cog(DocCog(bot))
