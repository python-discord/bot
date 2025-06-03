from datetime import UTC, datetime, timedelta
from typing import Literal

from async_rediscache import RedisCache
from dateutil.relativedelta import relativedelta
from discord import TextChannel, Thread
from discord.ext.commands import Cog, Context, group, has_any_role
from pydis_core.utils.scheduling import Scheduler

from bot.bot import Bot
from bot.constants import Channels, Emojis, MODERATION_ROLES
from bot.converters import DurationDelta
from bot.log import get_logger
from bot.utils import time
from bot.utils.time import TimestampFormats, discord_timestamp

log = get_logger(__name__)

SLOWMODE_MAX_DELAY = 21600  # seconds

COMMONLY_SLOWMODED_CHANNELS = {
    Channels.python_general: "python_general",
    Channels.discord_bots: "discord_bots",
    Channels.off_topic_0: "ot0",
}

MessageHolder = TextChannel | Thread | None


class Slowmode(Cog):
    """Commands for getting and setting slowmode delays of text channels."""

    # Stores the expiration timestamp in POSIX format for active slowmodes, keyed by channel ID.
    slowmode_expiration_cache = RedisCache()

    # Stores the original slowmode interval by channel ID, allowing its restoration after temporary slowmode expires.
    original_slowmode_cache = RedisCache()

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.scheduler = Scheduler(self.__class__.__name__)

    @group(name="slowmode", aliases=["sm"], invoke_without_command=True)
    async def slowmode_group(self, ctx: Context) -> None:
        """Get or set the slowmode delay for the text channel this was invoked in or a given text channel."""
        await ctx.send_help(ctx.command)

    @slowmode_group.command(name="get", aliases=["g"])
    async def get_slowmode(self, ctx: Context, channel: MessageHolder) -> None:
        """Get the slowmode delay for a text channel."""
        # Use the channel this command was invoked in if one was not given
        if channel is None:
            channel = ctx.channel

        humanized_delay = time.humanize_delta(seconds=channel.slowmode_delay)
        if await self.slowmode_expiration_cache.contains(channel.id):
            expiration_time = await self.slowmode_expiration_cache.get(channel.id)
            expiration_timestamp = discord_timestamp(expiration_time, TimestampFormats.RELATIVE)
            await ctx.send(
                f"The slowmode delay for {channel.mention} is {humanized_delay} and expires in {expiration_timestamp}."
            )
        else:
            await ctx.send(f"The slowmode delay for {channel.mention} is {humanized_delay}.")

    @slowmode_group.command(name="set", aliases=["s"])
    async def set_slowmode(
        self,
        ctx: Context,
        channel: MessageHolder,
        delay: DurationDelta | Literal["0s", "0seconds"],
        duration: DurationDelta | None = None
    ) -> None:
        """
        Set the slowmode delay for a text channel.

        Supports temporary slowmodes with the `duration` argument that automatically
        revert to the original delay after expiration.
        """
        # Use the channel this command was invoked in if one was not given
        if channel is None:
            channel = ctx.channel

        # Convert `dateutil.relativedelta.relativedelta` to `datetime.timedelta`
        # Must do this to get the delta in a particular unit of time
        if isinstance(delay, str):
            delay = relativedelta(seconds=0)

        slowmode_delay = time.relativedelta_to_timedelta(delay).total_seconds()
        humanized_delay = time.humanize_delta(delay)

        # Ensure the delay is within discord's limits
        if not slowmode_delay <= SLOWMODE_MAX_DELAY:
            log.info(
                f"{ctx.author} tried to set the slowmode delay of #{channel} to {humanized_delay}, "
                "which is not between 0 and 6 hours."
            )

            await ctx.send(
                f"{Emojis.cross_mark} The slowmode delay must be between 0 and 6 hours."
            )
            return

        if duration is not None:
            slowmode_duration = time.relativedelta_to_timedelta(duration).total_seconds()
            humanized_duration = time.humanize_delta(duration)

            expiration_time = datetime.now(tz=UTC) + timedelta(seconds=slowmode_duration)
            expiration_timestamp = discord_timestamp(expiration_time, TimestampFormats.RELATIVE)

            # Only update original_slowmode_cache if the last slowmode was not temporary.
            if not await self.slowmode_expiration_cache.contains(channel.id):
                await self.original_slowmode_cache.set(channel.id, channel.slowmode_delay)
            await self.slowmode_expiration_cache.set(channel.id, expiration_time.timestamp())

            self.scheduler.schedule_at(expiration_time, channel.id, self._revert_slowmode(channel.id))
            log.info(
                f"{ctx.author} set the slowmode delay for #{channel} to"
                f"{humanized_delay} which expires in {humanized_duration}."
            )
            await channel.edit(slowmode_delay=slowmode_delay)
            await ctx.send(
            f"{Emojis.check_mark} The slowmode delay for {channel.mention}"
            f" is now {humanized_delay} and expires in {expiration_timestamp}."
        )
        else:
            if await self.slowmode_expiration_cache.contains(channel.id):
                await self.slowmode_expiration_cache.delete(channel.id)
                await self.original_slowmode_cache.delete(channel.id)
                self.scheduler.cancel(channel.id)

            log.info(f"{ctx.author} set the slowmode delay for #{channel} to {humanized_delay}.")
            await channel.edit(slowmode_delay=slowmode_delay)
            await ctx.send(
                f"{Emojis.check_mark} The slowmode delay for {channel.mention} is now {humanized_delay}."
            )
        if channel.id in COMMONLY_SLOWMODED_CHANNELS:
            log.info(f"Recording slowmode change in stats for {channel.name}.")
            self.bot.stats.gauge(f"slowmode.{COMMONLY_SLOWMODED_CHANNELS[channel.id]}", slowmode_delay)

    async def _reschedule(self) -> None:
        log.trace("Rescheduling the expiration of temporary slowmodes from cache.")
        for channel_id, expiration in await self.slowmode_expiration_cache.items():
            expiration_datetime = datetime.fromtimestamp(expiration, tz=UTC)
            channel = self.bot.get_channel(channel_id)
            log.info(f"Rescheduling slowmode expiration for #{channel} ({channel_id}).")
            self.scheduler.schedule_at(expiration_datetime, channel_id, self._revert_slowmode(channel_id))

    async def _revert_slowmode(self, channel_id: int) -> None:
        original_slowmode = await self.original_slowmode_cache.get(channel_id)
        slowmode_delay = time.humanize_delta(seconds=original_slowmode)
        channel = self.bot.get_channel(channel_id)
        log.info(f"Slowmode in #{channel} ({channel.id}) has expired and has reverted to {slowmode_delay}.")
        await channel.edit(slowmode_delay=original_slowmode)
        await channel.send(
            f"{Emojis.check_mark} A previously applied slowmode has expired and has been reverted to {slowmode_delay}."
        )
        await self.slowmode_expiration_cache.delete(channel.id)
        await self.original_slowmode_cache.delete(channel.id)

    @slowmode_group.command(name="reset", aliases=["r"])
    async def reset_slowmode(self, ctx: Context, channel: MessageHolder) -> None:
        """Reset the slowmode delay for a text channel to 0 seconds."""
        await self.set_slowmode(ctx, channel, relativedelta(seconds=0))
        if channel is None:
            channel = ctx.channel
        if await self.slowmode_expiration_cache.contains(channel.id):
            await self.slowmode_expiration_cache.delete(channel.id)
            await self.original_slowmode_cache.delete(channel.id)
            self.scheduler.cancel(channel.id)

    async def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators to invoke the commands in this cog."""
        return await has_any_role(*MODERATION_ROLES).predicate(ctx)

    async def cog_load(self) -> None:
        """Wait for guild to become available and reschedule slowmodes which should expire."""
        await self.bot.wait_until_guild_available()
        await self._reschedule()

    async def cog_unload(self) -> None:
        """Cancel all scheduled tasks."""
        self.scheduler.cancel_all()


async def setup(bot: Bot) -> None:
    """Load the Slowmode cog."""
    await bot.add_cog(Slowmode(bot))
