from bot.bot import Bot


def setup(bot: Bot) -> None:
    """Load the Sync cog."""
    # Defer import to reduce side effects from importing the sync package.
    from ._cog import Sync
    bot.add_cog(Sync(bot))
