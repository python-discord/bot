
from bot.bot import Bot
from bot.exts.help_channels._cog import HelpForum


async def setup(bot: Bot) -> None:
    """Load the HelpForum cog."""
    await bot.add_cog(HelpForum(bot))
