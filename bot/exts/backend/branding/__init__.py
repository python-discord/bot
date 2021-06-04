from bot.bot import Bot
from bot.exts.backend.branding._cog import Branding


def setup(bot: Bot) -> None:
    """Load Branding cog."""
    bot.add_cog(Branding(bot))
