from bot.bot import Bot
from bot.exts.backend.branding._cog import Branding


async def setup(bot: Bot) -> None:
    """Load Branding cog."""
    await bot.add_cog(Branding(bot))
