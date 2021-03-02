from bot.bot import Bot
from bot.exts.backend.branding._cog import BrandingManager


def setup(bot: Bot) -> None:
    """Loads BrandingManager cog."""
    bot.add_cog(BrandingManager(bot))
