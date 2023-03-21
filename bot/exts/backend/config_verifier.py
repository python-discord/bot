from discord.ext.commands import Cog

from bot import constants
from bot.bot import Bot
from bot.log import get_logger

log = get_logger(__name__)


class ConfigVerifier(Cog):
    """Verify config on startup."""

    def __init__(self, bot: Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        """
        Verify channels.

        If any channels in config aren't present in server, log them in a warning.
        """
        await self.bot.wait_until_guild_available()
        server = self.bot.get_guild(constants.Guild.id)

        server_channel_ids = {channel.id for channel in server.channels}
        invalid_channels = [
            (channel_name, channel_id) for channel_name, channel_id in constants.Channels
            if channel_id not in server_channel_ids
        ]

        if invalid_channels:
            log.warning(f"Configured channels do not exist in server: {invalid_channels}.")


async def setup(bot: Bot) -> None:
    """Load the ConfigVerifier cog."""
    await bot.add_cog(ConfigVerifier(bot))
