import asyncio
import logging
import random
import typing as t
from datetime import datetime, timedelta
from enum import Enum

import async_timeout
import discord
from async_rediscache import RedisCache
from discord.ext import commands

from bot.bot import Bot
from bot.constants import Branding as BrandingConfig, Channels, Guild
from bot.decorators import mock_in_debug
from bot.exts.backend.branding._repository import BrandingRepository, Event, RemoteObject

log = logging.getLogger(__name__)


class AssetType(Enum):
    """
    Recognised Discord guild asset types.

    The value of each member corresponds exactly to a kwarg that can be passed to `Guild.edit`.
    """

    BANNER = "banner"
    ICON = "icon"


def compound_hash(objects: t.Iterable[RemoteObject]) -> str:
    """Compound hashes are cached to check for change in any of the member `objects`."""
    return "-".join(item.sha for item in objects)


class Branding(commands.Cog):
    """Guild branding management."""

    # RedisCache[
    #     "event_path": Path from root in the branding repo (str)
    #     "event_description": Markdown description (str)
    #     "event_duration": Human-readable date range or 'Fallback' (str)
    #     "banner_hash": Hash of the last applied banner (str)
    #     "icons_hash": Compound hash of icons in rotation (str)
    #     "last_rotation_timestamp": POSIX timestamp (float)
    # ]
    cache_information = RedisCache()

    # Cache holding icons in current rotation ~ the keys are download URLs (str) and the values are integers
    # corresponding to the amount of times each icon has been used in the current rotation
    cache_icons = RedisCache()

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

    async def apply_banner(self, banner: RemoteObject) -> None:
        """
        Apply `banner` to the guild and cache its hash.

        Banners should always be applied via this method in order to ensure that the last hash is cached.
        """
        await self.apply_asset(AssetType.BANNER, banner.download_url)
        await self.cache_information.set("banner_hash", banner.sha)

    async def rotate_icons(self) -> None:
        """
        Choose and apply the next-up icon in rotation.

        We keep track of the amount of times each icon has been used. The values in `cache_icons` can be understood
        to be iteration IDs. When an icon is chosen & applied, we bump its count, pushing it into the next iteration.

        Once the current iteration (lowest count in the cache) depletes, we move onto the next iteration.

        In the case that there is only 1 icon in the rotation and has already been applied, do nothing.
        """
        log.debug("Rotating icons")

        state = await self.cache_icons.to_dict()
        log.trace(f"Total icons in rotation: {len(state)}")

        if len(state) == 1 and 1 in state.values():
            log.debug("Aborting icon rotation: only 1 icon is available and has already been applied")
            return

        current_iteration = min(state.values())  # Choose iteration to draw from
        options = [download_url for download_url, times_used in state.items() if times_used == current_iteration]

        log.trace(f"Choosing from {len(options)} icons in iteration {current_iteration}")
        next_icon = random.choice(options)

        await self.apply_asset(AssetType.ICON, next_icon)
        await self.cache_icons.increment(next_icon)  # Push the icon into the next iteration

        timestamp = datetime.utcnow().timestamp()
        await self.cache_information.set("last_rotation_timestamp", timestamp)

    async def maybe_rotate_icons(self) -> None:
        """
        Call `rotate_icons` if the configured amount of time has passed since last rotation.

        We offset the calculated time difference into the future in order to avoid off-by-a-little-bit errors.
        Because there is work to be done before the timestamp is read and written, the next read will likely
        commence slightly under 24 hours after the last write.
        """
        log.debug("Checking if icons should rotate")

        last_rotation_timestamp = await self.cache_information.get("last_rotation_timestamp")

        if last_rotation_timestamp is None:  # Maiden case ~ never rotated
            await self.rotate_icons()

        last_rotation = datetime.fromtimestamp(last_rotation_timestamp)
        difference = (datetime.utcnow() - last_rotation) + timedelta(minutes=5)

        log.trace(f"Icons last rotated at {last_rotation} (difference: {difference})")

        if difference.days >= BrandingConfig.cycle_frequency:
            await self.rotate_icons()

    async def initiate_icon_rotation(self, available_icons: t.List[RemoteObject]) -> None:
        """
        Set up a new icon rotation.

        This function should be called whenever the set of `available_icons` changes. This is generally the case
        when we enter a new event, but potentially also when the assets of an on-going event change. In such cases,
        a reset of `cache_icons` is necessary, because it contains download URLs which may have gotten stale.
        """
        log.debug("Initiating new icon rotation")

        await self.cache_icons.clear()

        new_state = {icon.download_url: 0 for icon in available_icons}
        await self.cache_icons.update(new_state)

        log.trace(f"Icon rotation initiated for {len(new_state)} icons")

        await self.rotate_icons()
        await self.cache_information.set("icons_hash", compound_hash(available_icons))

    async def send_info_embed(self, channel_id: int) -> None:
        """
        Send the currently cached event description to `channel_id`.

        This function is called when entering a new event with the destination being #changelog. However, it can
        also be invoked on-demand by users.

        To support either case, we read information about the current event from `cache_information`. The caller
        is therefore responsible for making sure that the cache is up-to-date before calling this function.
        """
        log.debug(f"Sending event information event to channel id: {channel_id}")

        await self.bot.wait_until_guild_available()
        channel: t.Optional[discord.TextChannel] = self.bot.get_channel(channel_id)

        if channel is None:
            log.warning(f"Cannot send event information: channel {channel_id} not found!")
            return

        log.debug(f"Destination channel: #{channel.name}")

        embed = discord.Embed(
            description=await self.cache_information.get("event_description"),
            colour=discord.Colour.blurple(),
        )
        embed.set_footer(text=await self.cache_information.get("event_duration"))

        await channel.send(embed=embed)

    async def enter_event(self, event: Event) -> None:
        """
        Enter `event` and update information cache.

        From the outside, entering a new event is as simple as applying its branding to the guild and dispatching
        a notification to #changelog.

        However, internally we cache information to ensure that we:
        * Remember which event we're currently in across restarts
        * Provide an on-demand information embed without re-querying the branding repository

        An event change should always be handled via this function, as it ensures that the cache is populated.
        """
        log.debug(f"Entering new event: {event.path}")

        await self.apply_banner(event.banner)  # Only one asset ~ apply directly
        await self.initiate_icon_rotation(event.icons)  # Extra layer of abstraction to handle multiple assets

        # Cache event identity to avoid re-entry in case of restart
        await self.cache_information.set("event_path", event.path)

        # The following values are only stored for the purpose of presenting them to the users
        if event.meta.is_fallback:
            event_duration = "Fallback"
        else:
            fmt = "%B %d"  # Ex: August 23
            start_date = event.meta.start_date.strftime(fmt)
            end_date = event.meta.end_date.strftime(fmt)
            event_duration = f"{start_date} - {end_date}"

        await self.cache_information.set("event_duration", event_duration)
        await self.cache_information.set("event_description", event.meta.description)

        # Notify guild of new event ~ this reads the information that we cached above!
        await self.send_info_embed(Channels.change_log)

    # endregion
