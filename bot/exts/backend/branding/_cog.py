import asyncio
import contextlib
import random
import types
import typing as t
from datetime import timedelta
from enum import Enum
from operator import attrgetter

import discord
from arrow import Arrow
from async_rediscache import RedisCache
from discord.ext import commands, tasks

from bot.bot import Bot
from bot.constants import Branding as BrandingConfig, Channels, Colours, Guild, MODERATION_ROLES
from bot.decorators import mock_in_debug
from bot.exts.backend.branding._repository import BrandingRepository, Event, RemoteObject
from bot.log import get_logger

log = get_logger(__name__)


class AssetType(Enum):
    """
    Recognised Discord guild asset types.

    The value of each member corresponds exactly to a kwarg that can be passed to `Guild.edit`.
    """

    BANNER = "banner"
    ICON = "icon"


def compound_hash(objects: t.Iterable[RemoteObject]) -> str:
    """
    Join SHA attributes of `objects` into a single string.

    Compound hashes are cached to check for change in any of the member `objects`.
    """
    return "-".join(item.sha for item in objects)


def make_embed(title: str, description: str, *, success: bool) -> discord.Embed:
    """
    Construct simple response embed.

    If `success` is True, use green colour, otherwise red.

    For both `title` and `description`, empty string are valid values ~ fields will be empty.
    """
    colour = Colours.soft_green if success else Colours.soft_red
    return discord.Embed(title=title[:256], description=description[:4096], colour=colour)


def extract_event_duration(event: Event) -> str:
    """
    Extract a human-readable, year-agnostic duration string from `event`.

    In the case that `event` is a fallback event, resolves to 'Fallback'.

    For 1-day events, only the single date is shown, instead of a period.
    """
    if event.meta.is_fallback:
        return "Fallback"

    fmt = "%B %d"  # Ex: August 23
    start_date = event.meta.start_date.strftime(fmt)
    end_date = event.meta.end_date.strftime(fmt)

    if start_date == end_date:
        return start_date

    return f"{start_date} - {end_date}"


def extract_event_name(event: Event) -> str:
    """
    Extract title-cased event name from the path of `event`.

    An event with a path of 'events/black_history_month' will resolve to 'Black History Month'.
    """
    name = event.path.split("/")[-1]  # Inner-most directory name.
    words = name.split("_")  # Words from snake case.

    return " ".join(word.title() for word in words)


class Branding(commands.Cog):
    """
    Guild branding management.

    Extension responsible for automatic synchronisation of the guild's branding with the branding repository.
    Event definitions and assets are automatically discovered and applied as appropriate.

    All state is stored in Redis. The cog should therefore seamlessly transition across restarts and maintain
    a consistent icon rotation schedule for events with multiple icon assets.

    By caching hashes of banner & icon assets, we discover changes in currently applied assets and always keep
    the latest version applied.

    The command interface allows moderators+ to control the daemon or request asset synchronisation, while
    regular users can see information about the current event and the overall event schedule.
    """

    # RedisCache[
    #     "daemon_active": bool                   | If True, daemon starts on start-up. Controlled via commands.
    #     "event_path": str                       | Current event's path in the branding repo.
    #     "event_description": str                | Current event's Markdown description.
    #     "event_duration": str                   | Current event's human-readable date range.
    #     "banners_hash": str                     | Compound SHA of all banners in the current rotation.
    #     "icons_hash": str                       | Compound SHA of all icons in current rotation.
    #     "last_icon_rotation_timestamp": float   | POSIX UTC timestamp.
    #     "last_banner_rotation_timestamp": float | POSIX UTC timestamp.
    # ]
    cache_information = RedisCache()

    # Icons and banners in current rotation.
    # Keys (str) are download URLs, values (int) track the amount of times each
    # asset has been used in the current rotation.
    asset_caches = types.MappingProxyType({
        AssetType.ICON: RedisCache(namespace="Branding.icon_cache"),
        AssetType.BANNER: RedisCache(namespace="Branding.banner_cache")
    })

    # All available event names & durations. Cached by the daemon nightly; read by the calendar command.
    cache_events = RedisCache()

    def __init__(self, bot: Bot) -> None:
        """Instantiate repository abstraction & allow daemon to start."""
        self.bot = bot
        self.repository = BrandingRepository(bot)

    async def cog_load(self) -> None:
        """Carry out cog asynchronous initialisation."""
        await self.maybe_start_daemon()  # Start depending on cache.

    # region: Internal logic & state management

    @mock_in_debug(return_value=True)  # Mocked in development environment to prevent API spam.
    async def apply_asset(self, asset_type: AssetType, download_url: str) -> bool:
        """
        Download asset from `download_url` and apply it to PyDis as `asset_type`.

        Return a boolean indicating whether the application was successful.
        """
        log.info(f"Applying '{asset_type.value}' asset to the guild.")

        try:
            file = await self.repository.fetch_file(download_url)
        except Exception:
            log.exception(f"Failed to fetch '{asset_type.value}' asset.")
            return False

        await self.bot.wait_until_guild_available()
        pydis: discord.Guild = self.bot.get_guild(Guild.id)

        timeout = 10  # Seconds.
        try:
            async with asyncio.timeout(timeout):  # Raise after `timeout` seconds.
                await pydis.edit(**{asset_type.value: file})
        except discord.HTTPException:
            log.exception("Asset upload to Discord failed.")
            return False
        except TimeoutError:
            log.error(f"Asset upload to Discord timed out after {timeout} seconds.")
            return False
        else:
            log.trace("Asset uploaded successfully.")
            return True

    async def rotate_assets(self, asset_type: AssetType) -> bool:
        """
        Choose and apply the next-up asset in rotation.

        We keep track of the amount of times each asset has been used. The values in the cache can be understood
        to be iteration IDs. When an asset is chosen & applied, we bump its count, pushing it into the next iteration.

        Once the current iteration (lowest count in the cache) depletes, we move onto the next iteration.

        In the case that there is only 1 asset in the rotation and has already been applied, do nothing.

        Return a boolean indicating whether a new asset was applied successfully.
        """
        log.debug(f"Rotating {asset_type.value}s.")

        state = await self.asset_caches[asset_type].to_dict()
        log.trace(f"Total {asset_type.value}s in rotation: {len(state)}.")

        if not state:  # This would only happen if rotation not initiated, but we can handle gracefully.
            log.warning(f"Attempted {asset_type.value} rotation with an empty cache. This indicates wrong logic.")
            return False

        if len(state) == 1 and 1 in state.values():
            log.debug(f"Aborting {asset_type.value} rotation: only 1 asset is available and has already been applied.")
            return False

        current_iteration = min(state.values())  # Choose iteration to draw from.
        options = [download_url for download_url, times_used in state.items() if times_used == current_iteration]

        log.trace(f"Choosing from {len(options)} {asset_type.value}s in iteration {current_iteration}.")
        next_asset = random.choice(options)

        success = await self.apply_asset(asset_type, next_asset)

        if success:
            await self.asset_caches[asset_type].increment(next_asset)  # Push the asset into the next iteration.

            timestamp = Arrow.utcnow().timestamp()
            await self.cache_information.set(f"last_{asset_type.value}_rotation_timestamp", timestamp)

        return success

    async def maybe_rotate_assets(self, asset_type: AssetType) -> None:
        """
        Call `rotate_assets` if the configured amount of time has passed since last rotation.

        We offset the calculated time difference into the future to avoid off-by-a-little-bit errors. Because there
        is work to be done before the timestamp is read and written, the next read will likely commence slightly
        under 24 hours after the last write.
        """
        log.debug(f"Checking whether it's time for {asset_type.value}s to rotate.")

        last_rotation_timestamp = await self.cache_information.get(f"last_{asset_type.value}_rotation_timestamp")

        if last_rotation_timestamp is None:  # Maiden case ~ never rotated.
            await self.rotate_assets(asset_type)
            return

        last_rotation = Arrow.utcfromtimestamp(last_rotation_timestamp)
        difference = (Arrow.utcnow() - last_rotation) + timedelta(minutes=5)

        log.trace(f"{asset_type.value.title()}s last rotated at {last_rotation} (difference: {difference}).")

        if difference.days >= BrandingConfig.cycle_frequency:
            await self.rotate_assets(asset_type)

    async def initiate_rotation(self, asset_type: AssetType, available_assets: list[RemoteObject]) -> None:
        """
        Set up a new asset rotation.

        This function should be called whenever available asset groups change. This is generally the case when we enter
        a new event, but potentially also when the assets of an on-going event change. In such cases, a reset
        of the cache is necessary, because it contains download URLs which may have gotten stale.

        This function does not upload a new asset!
        """
        log.debug(f"Initiating new {asset_type.value} rotation.")

        await self.asset_caches[asset_type].clear()

        new_state = {asset.download_url: 0 for asset in available_assets}
        await self.asset_caches[asset_type].update(new_state)

        log.trace(f"{asset_type.value.title()} rotation initiated for {len(new_state)} assets.")

        await self.cache_information.set(f"{asset_type.value}s_hash", compound_hash(available_assets))

    async def send_info_embed(self, channel_id: int, *, is_notification: bool) -> None:
        """
        Send the currently cached event description to `channel_id`.

        When `is_notification` holds, a short contextual message for the #changelog channel is added.

        We read event information from `cache_information`. The caller is therefore responsible for making
        sure that the cache is up-to-date before calling this function.
        """
        log.debug(f"Sending event information event to channel: {channel_id} ({is_notification=}).")

        await self.bot.wait_until_guild_available()
        channel: discord.TextChannel | None = self.bot.get_channel(channel_id)

        if channel is None:
            log.warning(f"Cannot send event information: channel {channel_id} not found!")
            return

        log.trace(f"Destination channel: #{channel.name}.")

        description = await self.cache_information.get("event_description")
        duration = await self.cache_information.get("event_duration")

        if None in (description, duration):
            content = None
            embed = make_embed("No event in cache", "Is the daemon enabled?", success=False)

        else:
            content = "Python Discord is entering a new event!" if is_notification else None
            embed = discord.Embed(description=description[:4096], colour=discord.Colour.og_blurple())
            embed.set_footer(text=duration[:4096])

        await channel.send(content=content, embed=embed)

    async def enter_event(self, event: Event) -> tuple[bool, bool]:
        """
        Apply `event` assets and update information cache.

        We cache `event` information to ensure that we:
        * Remember which event we're currently in across restarts
        * Provide an on-demand informational embed without re-querying the branding repository

        An event change should always be handled via this function, as it ensures that the cache is populated.

        The #changelog notification is omitted when `event` is fallback, or already applied.

        Return a 2-tuple indicating whether the banner, and the icon, were applied successfully.
        """
        log.info(f"Entering event: '{event.path}'.")

        # Prepare and apply new icon and banner rotations
        await self.initiate_rotation(AssetType.ICON, event.icons)
        await self.initiate_rotation(AssetType.BANNER, event.banners)

        icon_success = await self.rotate_assets(AssetType.ICON)
        banner_success = await self.rotate_assets(AssetType.BANNER)

        # This will only be False in the case of a manual same-event re-synchronisation.
        event_changed = event.path != await self.cache_information.get("event_path")

        # Cache event identity to avoid re-entry in case of restart.
        await self.cache_information.set("event_path", event.path)

        # Cache information shown in the 'about' embed.
        await self.populate_cache_event_description(event)

        # Notify guild of new event ~ this reads the information that we cached above.
        if event_changed and not event.meta.is_fallback:
            await self.send_info_embed(Channels.changelog, is_notification=True)
        else:
            log.trace("Omitting #changelog notification. Event has not changed, or new event is fallback.")

        return banner_success, icon_success

    async def synchronise(self) -> tuple[bool, bool]:
        """
        Fetch the current event and delegate to `enter_event`.

        This is a convenience function to force synchronisation via a command. It should generally only be used
        in a recovery scenario. In the usual case, the daemon already has an `Event` instance and can pass it
        to `enter_event` directly.

        Return a 2-tuple indicating whether the banner, and the icon, were applied successfully.
        """
        log.debug("Synchronise: fetching current event.")

        current_event, available_events = await self.repository.get_current_event()

        await self.populate_cache_events(available_events)

        if current_event is None:
            log.error("Failed to fetch event. Cannot synchronise!")
            return False, False

        return await self.enter_event(current_event)

    async def populate_cache_events(self, events: list[Event]) -> None:
        """
        Clear `cache_events` and re-populate with names and durations of `events`.

        For each event, we store its name and duration string. This is the information presented to users in the
        calendar command. If a format change is needed, it has to be done here.

        The cache does not store the fallback event, as it is not shown in the calendar.
        """
        log.debug("Populating events cache.")

        await self.cache_events.clear()

        no_fallback = [event for event in events if not event.meta.is_fallback]
        chronological_events = sorted(no_fallback, key=attrgetter("meta.start_date"))

        log.trace(f"Writing {len(chronological_events)} events (fallback omitted).")

        with contextlib.suppress(ValueError):  # Cache raises when updated with an empty dict.
            await self.cache_events.update({
                extract_event_name(event): extract_event_duration(event)
                for event in chronological_events
            })

    async def populate_cache_event_description(self, event: Event) -> None:
        """
        Cache `event` description & duration.

        This should be called when entering a new event, and can be called periodically to ensure that the cache
        holds fresh information in the case that the event remains the same, but its description changes.

        The duration is stored formatted for the frontend. It is not intended to be used programmatically.
        """
        log.debug("Caching event description & duration.")

        await self.cache_information.set("event_description", event.meta.description)
        await self.cache_information.set("event_duration", extract_event_duration(event))

    # endregion
    # region: Daemon

    async def maybe_start_daemon(self) -> None:
        """
        Start the daemon depending on cache state.

        The daemon will only start if it has been explicitly enabled via a command.
        """
        log.debug("Checking whether daemon should start.")

        should_begin: bool | None = await self.cache_information.get("daemon_active")  # None if never set!

        if should_begin:
            self.daemon_loop.start()

    async def cog_unload(self) -> None:
        """
        Cancel the daemon in case of cog unload.

        This is **not** done automatically! The daemon otherwise remains active in the background.
        """
        log.debug("Cog unload: cancelling daemon.")

        self.daemon_loop.cancel()

    async def daemon_main(self) -> None:
        """
        Synchronise guild & caches with branding repository.

        Pull the currently active event from the branding repository and check whether it matches the currently
        active event in the cache. If not, apply the new event.

        However, it is also possible that an event's assets change as it's active. To account for such cases,
        we check the banner & icons hashes against the currently cached values. If there is a mismatch, each
        specific asset is re-applied.
        """
        log.info("Daemon main: checking current event.")

        new_event, available_events = await self.repository.get_current_event()

        await self.populate_cache_events(available_events)

        if new_event is None:
            log.warning("Daemon main: failed to get current event from branding repository, will do nothing.")
            return

        if new_event.path != await self.cache_information.get("event_path"):
            log.debug("Daemon main: new event detected!")
            await self.enter_event(new_event)
            return

        await self.populate_cache_event_description(new_event)  # Cache fresh frontend info in case of change.

        log.trace("Daemon main: event has not changed, checking for change in assets.")

        if compound_hash(new_event.banners) != await self.cache_information.get("banners_hash"):
            log.debug("Daemon main: detected banner change.")
            await self.initiate_rotation(AssetType.BANNER, new_event.banners)
            await self.rotate_assets(AssetType.BANNER)
        else:
            await self.maybe_rotate_assets(AssetType.BANNER)

        if compound_hash(new_event.icons) != await self.cache_information.get("icons_hash"):
            log.debug("Daemon main: detected icon change.")
            await self.initiate_rotation(AssetType.ICON, new_event.icons)
            await self.rotate_assets(AssetType.ICON)
        else:
            await self.maybe_rotate_assets(AssetType.ICON)

    @tasks.loop(hours=24)
    async def daemon_loop(self) -> None:
        """
        Call `daemon_main` every 24 hours.

        The scheduler maintains an exact 24-hour frequency even if this coroutine takes time to complete. If the
        coroutine is started at 00:01 and completes at 00:05, it will still be started at 00:01 the next day.
        """
        log.trace("Daemon loop: calling daemon main.")

        try:
            await self.daemon_main()
        except Exception:
            log.exception("Daemon loop: failed with an unhandled exception!")

    @daemon_loop.before_loop
    async def daemon_before(self) -> None:
        """
        Call `daemon_loop` immediately, then block the loop until the next-up UTC midnight.

        The first iteration is invoked directly such that synchronisation happens immediately after daemon start.
        We then calculate the time until the next-up midnight and sleep before letting `daemon_loop` begin.
        """
        log.trace("Daemon before: performing start-up iteration.")

        await self.daemon_loop()

        log.trace("Daemon before: calculating time to sleep before loop begins.")
        now = Arrow.utcnow()

        # The actual midnight moment is offset into the future to prevent issues with imprecise sleep.
        tomorrow = now.shift(days=1)
        midnight = tomorrow.replace(hour=0, minute=1, second=0, microsecond=0)

        sleep_secs = (midnight - now).total_seconds()
        log.trace(f"Daemon before: sleeping {sleep_secs} seconds before next-up midnight: {midnight}.")

        await asyncio.sleep(sleep_secs)

    # endregion
    # region: Command interface (branding)

    @commands.group(name="branding")
    async def branding_group(self, ctx: commands.Context) -> None:
        """Control the branding cog."""
        if not ctx.invoked_subcommand:
            await ctx.send_help(ctx.command)

    @branding_group.command(name="about", aliases=("current", "event"))
    async def branding_about_cmd(self, ctx: commands.Context) -> None:
        """Show the current event's description and duration."""
        await self.send_info_embed(ctx.channel.id, is_notification=False)

    @commands.has_any_role(*MODERATION_ROLES)
    @branding_group.command(name="sync")
    async def branding_sync_cmd(self, ctx: commands.Context) -> None:
        """
        Force branding synchronisation.

        Show which assets have failed to synchronise, if any.
        """
        async with ctx.typing():
            banner_success, icon_success = await self.synchronise()

        failed_assets = ", ".join(
            name
            for name, status in [("banner", banner_success), ("icon", icon_success)]
            if status is False
        )

        if failed_assets:
            resp = make_embed("Synchronisation unsuccessful", f"Failed to apply: {failed_assets}.", success=False)
            resp.set_footer(text="Check log for details.")
        else:
            resp = make_embed("Synchronisation successful", "Assets have been applied.", success=True)

        await ctx.send(embed=resp)

    # endregion
    # region: Command interface (branding calendar)

    @branding_group.group(name="calendar", aliases=("schedule", "events"))
    async def branding_calendar_group(self, ctx: commands.Context) -> None:
        """
        Show the current event calendar.

        We draw event information from `cache_events` and use each key-value pair to create a field in the response
        embed. As such, we do not need to query the API to get event information. The cache is automatically
        re-populated by the daemon whenever it makes a request. A moderator+ can also explicitly request a cache
        refresh using the 'refresh' subcommand.

        Due to Discord limitations, we only show up to 25 events. This is entirely sufficient at the time of writing.
        In the case that we find ourselves with more than 25 events, a warning log will alert core devs.

        In the future, we may be interested in a field-paginating solution.
        """
        if ctx.invoked_subcommand:
            # If you're wondering why this works: when the 'refresh' subcommand eventually re-invokes
            # this group, the attribute will be automatically set to None by the framework.
            return

        available_events = await self.cache_events.to_dict()
        log.trace(f"Found {len(available_events)} cached events available for calendar view.")

        if not available_events:
            resp = make_embed("No events found!", "Cache may be empty, try `branding calendar refresh`.", success=False)
            await ctx.send(embed=resp)
            return

        embed = discord.Embed(title="Current event calendar", colour=discord.Colour.og_blurple())

        # Because Discord embeds can only contain up to 25 fields, we only show the first 25.
        first_25 = list(available_events.items())[:25]

        if len(first_25) != len(available_events):  # Alert core devs that a paginating solution is now necessary.
            log.warning(f"There are {len(available_events)} events, but the calendar view can only display 25.")

        for name, duration in first_25:
            embed.add_field(name=name[:256], value=duration[:1024])

        embed.set_footer(text="Otherwise, the fallback season is used.")

        await ctx.send(embed=embed)

    @commands.has_any_role(*MODERATION_ROLES)
    @branding_calendar_group.command(name="refresh")
    async def branding_calendar_refresh_cmd(self, ctx: commands.Context) -> None:
        """
        Refresh event cache and show current event calendar.

        Supplementary subcommand allowing force-refreshing the event cache. Implemented as a subcommand because
        unlike the supergroup, it requires moderator privileges.
        """
        log.info("Performing command-requested event cache refresh.")

        async with ctx.typing():
            available_events = await self.repository.get_events()
            await self.populate_cache_events(available_events)

        await ctx.invoke(self.branding_calendar_group)

    # endregion
    # region: Command interface (branding daemon)

    @commands.has_any_role(*MODERATION_ROLES)
    @branding_group.group(name="daemon", aliases=("d",))
    async def branding_daemon_group(self, ctx: commands.Context) -> None:
        """Control the branding cog's daemon."""
        if not ctx.invoked_subcommand:
            await ctx.send_help(ctx.command)

    @branding_daemon_group.command(name="enable", aliases=("start", "on"))
    async def branding_daemon_enable_cmd(self, ctx: commands.Context) -> None:
        """Enable the branding daemon."""
        await self.cache_information.set("daemon_active", True)

        if self.daemon_loop.is_running():
            resp = make_embed("Daemon is already enabled!", "", success=False)
        else:
            self.daemon_loop.start()
            resp = make_embed("Daemon enabled!", "It will now automatically awaken on start-up.", success=True)

        await ctx.send(embed=resp)

    @branding_daemon_group.command(name="disable", aliases=("stop", "off"))
    async def branding_daemon_disable_cmd(self, ctx: commands.Context) -> None:
        """Disable the branding daemon."""
        await self.cache_information.set("daemon_active", False)

        if self.daemon_loop.is_running():
            self.daemon_loop.cancel()
            resp = make_embed("Daemon disabled!", "It will not awaken on start-up.", success=True)
        else:
            resp = make_embed("Daemon is already disabled!", "", success=False)

        await ctx.send(embed=resp)

    @branding_daemon_group.command(name="status")
    async def branding_daemon_status_cmd(self, ctx: commands.Context) -> None:
        """Check whether the daemon is currently enabled."""
        if self.daemon_loop.is_running():
            resp = make_embed("Daemon is enabled", "Use `branding daemon disable` to stop.", success=True)
        else:
            resp = make_embed("Daemon is disabled", "Use `branding daemon enable` to start.", success=False)

        await ctx.send(embed=resp)

    # endregion
