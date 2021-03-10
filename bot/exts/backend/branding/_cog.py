import asyncio
import logging
from enum import Enum

import async_timeout
import discord
from discord.ext import commands

from bot.bot import Bot
from bot.constants import Guild
from bot.decorators import mock_in_debug
from bot.exts.backend.branding._repository import BrandingRepository

log = logging.getLogger(__name__)


class AssetType(Enum):
    """
    Recognised Discord guild asset types.

    The value of each member corresponds exactly to a kwarg that can be passed to `Guild.edit`.
    """

    BANNER = "banner"
    ICON = "icon"


class Branding(commands.Cog):
    """Guild branding management."""

    def __init__(self, bot: Bot) -> None:
        """Instantiate repository abstraction."""
        self.bot = bot
        self.repository = BrandingRepository(bot)

    # region: Internal utility

    @mock_in_debug(return_value=None)
    async def apply_asset(self, asset_type: AssetType, download_url: str) -> None:
        """
        Download asset from `download_url` and apply it to PyDis as `asset_type`.

        This function is mocked in the development environment in order to prevent API spam during testing.
        Decorator should be temporarily removed in order to test internal methodology.
        """
        log.info(f"Applying {asset_type.value} asset to the guild")

        file = await self.repository.fetch_file(download_url)

        if file is None:
            log.error(f"Failed to download {asset_type.value} from branding repository!")
            return

        await self.bot.wait_until_guild_available()
        pydis: discord.Guild = self.bot.get_guild(Guild.id)

        timeout = 10  # Seconds
        try:
            with async_timeout.timeout(timeout):
                await pydis.edit(**{asset_type.value: file})
        except discord.HTTPException as http_exc:
            log.error(f"Asset upload to Discord failed: {http_exc}")
        except asyncio.TimeoutError:
            log.error(f"Asset upload to Discord timed out after {timeout} seconds!")
        else:
            log.debug("Asset uploaded successfully!")

    # endregion
