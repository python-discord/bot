import asyncio
import logging
import random
import typing as t
from datetime import datetime, time, timedelta
from enum import Enum
from operator import attrgetter

import async_timeout
import discord
from async_rediscache import RedisCache
from discord.ext import commands, tasks

from bot.bot import Bot
from bot.constants import Branding as BrandingConfig, Channels, Colours, Guild, MODERATION_ROLES
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


def make_embed(title: str, description: str, *, success: bool) -> discord.Embed:
    """
    Construct simple response embed.

    If `success` is True, use green colour, otherwise red.

    For both `title` and `description`, empty string are valid values ~ fields will be empty.
    """
    colour = Colours.soft_green if success else Colours.soft_red
    return discord.Embed(title=title, description=description, colour=colour)


def extract_event_duration(event: Event) -> str:
    """
    Extract a human-readable, year-agnostic duration string from `event`.

    In the case that `event` is a fallback event, resolves to 'Fallback'.
    """
    if event.meta.is_fallback:
        return "Fallback"

    fmt = "%B %d"  # Ex: August 23
    start_date = event.meta.start_date.strftime(fmt)
    end_date = event.meta.end_date.strftime(fmt)

    return f"{start_date} - {end_date}"


def extract_event_name(event: Event) -> str:
    """
    Extract title-cased event name from the path of `event`.

    An event with a path of 'events/black_history_month' will resolve to 'Black History Month'.
    """
    name = event.path.split("/")[-1]  # Inner-most directory name
    words = name.split("_")  # Words from snake case

    return " ".join(word.title() for word in words)


class Branding(commands.Cog):
    """Guild branding management."""

    # RedisCache[
    #     "daemon_active": If True, daemon auto-starts; controlled via commands (bool)
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

    # Cache holding all available event names & their durations; this is cached by the daemon and read by
    # the calendar command with the intention of preventing API spam; doesn't contain the fallback event
    cache_events = RedisCache()

    def __init__(self, bot: Bot) -> None:
        """Instantiate repository abstraction & allow daemon to start."""
        self.bot = bot
        self.repository = BrandingRepository(bot)

        self.bot.loop.create_task(self.maybe_start_daemon())  # Start depending on cache

    # region: Internal utility

    @mock_in_debug(return_value=True)
    async def apply_asset(self, asset_type: AssetType, download_url: str) -> bool:
        """
        Download asset from `download_url` and apply it to PyDis as `asset_type`.

        This function is mocked in the development environment in order to prevent API spam during testing.
        Decorator should be temporarily removed in order to test internal methodology.

        Returns a boolean indicating whether the application was successful.
        """
        log.info(f"Applying {asset_type.value} asset to the guild")

        file = await self.repository.fetch_file(download_url)

        if file is None:
            log.error(f"Failed to download {asset_type.value} from branding repository!")
            return False

        await self.bot.wait_until_guild_available()
        pydis: discord.Guild = self.bot.get_guild(Guild.id)

        timeout = 10  # Seconds
        try:
            with async_timeout.timeout(timeout):
                await pydis.edit(**{asset_type.value: file})
        except discord.HTTPException as http_exc:
            log.error(f"Asset upload to Discord failed: {http_exc}")
            return False
        except asyncio.TimeoutError:
            log.error(f"Asset upload to Discord timed out after {timeout} seconds!")
            return False
        else:
            log.debug("Asset uploaded successfully!")
            return True

    async def apply_banner(self, banner: RemoteObject) -> bool:
        """
        Apply `banner` to the guild and cache its hash if successful.

        Banners should always be applied via this method in order to ensure that the last hash is cached.

        Returns a boolean indicating whether the application was successful.
        """
        success = await self.apply_asset(AssetType.BANNER, banner.download_url)

        if success:
            await self.cache_information.set("banner_hash", banner.sha)

        return success

    async def rotate_icons(self) -> bool:
        """
        Choose and apply the next-up icon in rotation.

        We keep track of the amount of times each icon has been used. The values in `cache_icons` can be understood
        to be iteration IDs. When an icon is chosen & applied, we bump its count, pushing it into the next iteration.

        Once the current iteration (lowest count in the cache) depletes, we move onto the next iteration.

        In the case that there is only 1 icon in the rotation and has already been applied, do nothing.

        Returns a boolean indicating whether a new icon was applied successfully.
        """
        log.debug("Rotating icons")

        state = await self.cache_icons.to_dict()
        log.trace(f"Total icons in rotation: {len(state)}")

        if len(state) == 1 and 1 in state.values():
            log.debug("Aborting icon rotation: only 1 icon is available and has already been applied")
            return False

        current_iteration = min(state.values())  # Choose iteration to draw from
        options = [download_url for download_url, times_used in state.items() if times_used == current_iteration]

        log.trace(f"Choosing from {len(options)} icons in iteration {current_iteration}")
        next_icon = random.choice(options)

        success = await self.apply_asset(AssetType.ICON, next_icon)

        if success:
            await self.cache_icons.increment(next_icon)  # Push the icon into the next iteration

            timestamp = datetime.utcnow().timestamp()
            await self.cache_information.set("last_rotation_timestamp", timestamp)

        return success

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
            return

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

        This function does not upload a new icon!
        """
        log.debug("Initiating new icon rotation")

        await self.cache_icons.clear()

        new_state = {icon.download_url: 0 for icon in available_icons}
        await self.cache_icons.update(new_state)

        log.trace(f"Icon rotation initiated for {len(new_state)} icons")

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

    async def enter_event(self, event: Event) -> t.Tuple[bool, bool]:
        """
        Enter `event` and update information cache.

        From the outside, entering a new event is as simple as applying its branding to the guild and dispatching
        a notification to #changelog.

        However, internally we cache information to ensure that we:
        * Remember which event we're currently in across restarts
        * Provide an on-demand information embed without re-querying the branding repository

        An event change should always be handled via this function, as it ensures that the cache is populated.

        Returns a 2-tuple indicating whether the banner, and the icon, were applied successfully.
        """
        log.debug(f"Entering new event: {event.path}")

        banner_success = await self.apply_banner(event.banner)  # Only one asset ~ apply directly

        await self.initiate_icon_rotation(event.icons)  # Prepare a new rotation
        icon_success = await self.rotate_icons()  # Apply an icon from the new rotation

        # Cache event identity to avoid re-entry in case of restart
        await self.cache_information.set("event_path", event.path)

        # The following values are only stored for the purpose of presenting them to the users
        await self.cache_information.set("event_duration", extract_event_duration(event))
        await self.cache_information.set("event_description", event.meta.description)

        # Notify guild of new event ~ this reads the information that we cached above!
        await self.send_info_embed(Channels.change_log)

        return banner_success, icon_success

    async def synchronise(self) -> t.Tuple[bool, bool]:
        """
        Fetch the current event and delegate to `enter_event`.

        This is a convenience wrapper to force synchronisation either via a command, or when the daemon starts
        with an empty cache. It is generally only used in a recovery scenario. In the usual case, the daemon
        already has an `Event` instance and can pass it to `enter_event` directly.

        Returns a 2-tuple indicating whether the banner, and the icon, were applied successfully.
        """
        log.debug("Synchronise: fetching current event")

        current_event, available_events = await self.repository.get_current_event()

        await self.populate_cache_events(available_events)

        if current_event is None:
            log.error("Failed to fetch event ~ cannot synchronise!")
            return False, False

        return await self.enter_event(current_event)

    async def populate_cache_events(self, events: t.List[Event]) -> None:
        """
        Clear `cache_events` and re-populate with names and durations of `events`.

        For each event, we store its name and duration string. This is the information presented to users in the
        calendar command. If a format change is needed, it has to be done here.

        The cache does not store the fallback event, as it is not shown in the calendar.
        """
        log.debug(f"Populating events cache with {len(events)} events")

        await self.cache_events.clear()

        no_fallback = [event for event in events if not event.meta.is_fallback]
        chronological_events = sorted(no_fallback, key=attrgetter("meta.start_date"))

        await self.cache_events.update({
            extract_event_name(event): extract_event_duration(event)
            for event in chronological_events
        })

    # endregion
    # region: Daemon

    async def maybe_start_daemon(self) -> None:
        """
        Start the daemon depending on cache state.

        The daemon will only start if it's been previously explicitly enabled via a command.
        """
        log.debug("Checking whether daemon is enabled")

        should_begin: t.Optional[bool] = await self.cache_information.get("daemon_active")  # None if never set!

        if should_begin:
            self.daemon_main.start()

    async def cog_unload(self) -> None:
        """
        Cancel the daemon in case of cog unload.

        This is **not** done automatically! The daemon otherwise remains active in the background.
        """
        log.debug("Cog unload: cancelling daemon")

        self.daemon_main.cancel()

    @tasks.loop(hours=24)
    async def daemon_main(self) -> None:
        """
        Periodically synchronise guild & caches with branding repository.

        This function executes every 24 hours at midnight. We pull the currently active event from the branding
        repository and check whether it matches the currently active event. If not, we apply the new event.

        However, it is also possible that an event's assets change as it's active. To account for such cases,
        we check the banner & icons hashes against the currently cached values. If there is a mismatch, the
        specific asset is re-applied.

        As such, the guild should always remain synchronised with the branding repository. However, the #changelog
        notification is only sent in the case of entering a new event ~ no change in an on-going event will trigger
        a new notification to be sent.
        """
        log.debug("Daemon awakens: checking current event")

        new_event, available_events = await self.repository.get_current_event()

        await self.populate_cache_events(available_events)

        if new_event is None:
            log.warning("Failed to get current event from the branding repository, daemon will do nothing!")
            return

        if new_event.path != await self.cache_information.get("event_path"):
            log.debug("New event detected!")
            await self.enter_event(new_event)
            return

        log.debug("Event has not changed, checking for change in assets")

        if new_event.banner.sha != await self.cache_information.get("banner_hash"):
            log.debug("Detected same-event banner change!")
            await self.apply_banner(new_event.banner)

        if compound_hash(new_event.icons) != await self.cache_information.get("icons_hash"):
            log.debug("Detected same-event icon change!")
            await self.initiate_icon_rotation(new_event.icons)
            await self.rotate_icons()
        else:
            await self.maybe_rotate_icons()

    @daemon_main.before_loop
    async def daemon_before(self) -> None:
        """
        Wait until the next-up UTC midnight before letting `daemon_main` begin.

        This function allows the daemon to keep a consistent schedule across restarts.

        We check for a special case in which the cog's cache is empty. This indicates that we have never entered
        an event (on first start-up), or that there was a cache loss. In either case, the current event gets
        applied immediately, to avoid leaving the cog in an empty state.
        """
        log.debug("Calculating time for daemon to sleep before first awakening")

        current_event = await self.cache_information.get("event_path")

        if current_event is None:  # Maiden case ~ first start or cache loss
            log.debug("Event cache is empty (indicating maiden case), invoking synchronisation")
            await self.synchronise()

        now = datetime.utcnow()

        # The actual midnight moment is offset into the future in order to prevent issues with imprecise sleep
        tomorrow = now + timedelta(days=1)
        midnight = datetime.combine(tomorrow, time(minute=1))

        sleep_secs = (midnight - now).total_seconds()

        log.debug(f"Sleeping {sleep_secs} seconds before next-up midnight at {midnight}")
        await asyncio.sleep(sleep_secs)

    # endregion
    # region: Command interface (branding)

    @commands.group(name="branding")
    async def branding_group(self, ctx: commands.Context) -> None:
        """Control the branding cog."""
        if not ctx.invoked_subcommand:
            await ctx.send_help(ctx.command)

    @branding_group.command(name="about")
    async def branding_about_cmd(self, ctx: commands.Context) -> None:
        """Show the current event description."""
        await self.send_info_embed(ctx.channel.id)

    @commands.has_any_role(*MODERATION_ROLES)
    @branding_group.command(name="sync")
    async def branding_sync_cmd(self, ctx: commands.Context) -> None:
        """Force branding synchronisation."""
        async with ctx.typing():
            await self.synchronise()

        resp = make_embed(
            "Synchronisation complete",
            "If something doesn't look right, check log for errors.",
            success=True,
        )
        await ctx.send(embed=resp)

    # endregion
    # region: Command interface (branding calendar)

    @branding_group.group(name="calendar", aliases=("schedule",))
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
            # this group, the attribute will be automatically set to None by the framework
            return

        available_events = await self.cache_events.to_dict()
        log.debug(f"Found {len(available_events)} cached events available for calendar view")

        if not available_events:
            resp = make_embed("No events found!", "Cache may be empty, try `branding calendar refresh`.", success=False)
            await ctx.send(embed=resp)
            return

        embed = discord.Embed(title="Current event calendar", colour=discord.Colour.blurple())

        # Because a Discord embed can only contain up to 25 fields, we only show the first 25
        first_25 = list(available_events.items())[:25]

        if len(first_25) != len(available_events):  # Alert core devs that a paginating solution is now necessary
            log.warning(f"There are {len(available_events)} events, but the calendar view can only display 25!")

        for name, duration in first_25:
            embed.add_field(name=name, value=duration)

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
        log.debug("Performing command-requested event cache refresh")

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

        if self.daemon_main.is_running():
            resp = make_embed("Daemon is already enabled!", "", success=False)
        else:
            self.daemon_main.start()
            resp = make_embed("Daemon enabled!", "It will now automatically awaken on start-up.", success=True)

        await ctx.send(embed=resp)

    @branding_daemon_group.command(name="disable", aliases=("stop", "off"))
    async def branding_daemon_disable_cmd(self, ctx: commands.Context) -> None:
        """Disable the branding daemon."""
        await self.cache_information.set("daemon_active", False)

        if self.daemon_main.is_running():
            self.daemon_main.cancel()
            resp = make_embed("Daemon disabled!", "It will not awaken on start-up.", success=True)
        else:
            resp = make_embed("Daemon is already disabled!", "", success=False)

        await ctx.send(embed=resp)

    @branding_daemon_group.command(name="status")
    async def branding_daemon_status_cmd(self, ctx: commands.Context) -> None:
        """Check whether the daemon is currently enabled."""
        if self.daemon_main.is_running():
            resp = make_embed("Daemon is enabled", "Use `branding daemon disable` to stop.", success=True)
        else:
            resp = make_embed("Daemon is disabled", "Use `branding daemon enable` to start.", success=False)

        await ctx.send(embed=resp)

    # endregion
