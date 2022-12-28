
from bot.bot import Bot
from bot.constants import HelpChannels
from bot.exts.help_channels._cog import HelpForum
from bot.log import get_logger

log = get_logger(__name__)


async def setup(bot: Bot) -> None:
    """Load the HelpForum cog."""
    if not HelpChannels.enable:
        log.warning("HelpChannel.enabled set to false, not loading help channel cog.")
        return
    await bot.add_cog(HelpForum(bot))
