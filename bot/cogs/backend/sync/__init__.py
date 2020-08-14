from bot.bot import Bot


def setup(bot: Bot) -> None:
    """Load the Sync cog."""
    from ._cog import Sync
    bot.add_cog(Sync(bot))
