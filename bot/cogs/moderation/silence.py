import asyncio
import logging
from contextlib import suppress
from typing import Optional

from discord import TextChannel
from discord.ext import commands, tasks
from discord.ext.commands import Context

from bot.bot import Bot
from bot.constants import Channels, Emojis, Guild, MODERATION_ROLES, Roles
from bot.converters import HushDurationConverter
from bot.utils.checks import with_role_check

log = logging.getLogger(__name__)


class SilenceNotifier(tasks.Loop):
    """Loop notifier for posting notices to `alert_channel` containing added channels."""

    def __init__(self, alert_channel: TextChannel):
        super().__init__(self._notifier, seconds=1, minutes=0, hours=0, count=None, reconnect=True, loop=None)
        self._silenced_channels = {}
        self._alert_channel = alert_channel

    def add_channel(self, channel: TextChannel) -> None:
        """Add channel to `_silenced_channels` and start loop if not launched."""
        if not self._silenced_channels:
            self.start()
            log.info("Starting notifier loop.")
        self._silenced_channels[channel] = self._current_loop

    def remove_channel(self, channel: TextChannel) -> None:
        """Remove channel from `_silenced_channels` and stop loop if no channels remain."""
        with suppress(KeyError):
            del self._silenced_channels[channel]
            if not self._silenced_channels:
                self.stop()
                log.info("Stopping notifier loop.")

    async def _notifier(self) -> None:
        """Post notice of `_silenced_channels` with their silenced duration to `_alert_channel` periodically."""
        # Wait for 15 minutes between notices with pause at start of loop.
        if self._current_loop and not self._current_loop/60 % 15:
            log.debug(
                f"Sending notice with channels: "
                f"{', '.join(f'#{channel} ({channel.id})' for channel in self._silenced_channels)}."
            )
            channels_text = ', '.join(
                f"{channel.mention} for {(self._current_loop-start)//60} min"
                for channel, start in self._silenced_channels.items()
            )
            await self._alert_channel.send(f"<@&{Roles.moderators}> currently silenced channels: {channels_text}")


class Silence(commands.Cog):
    """Commands for stopping channel messages for `verified` role in a channel."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.muted_channels = set()
        self._get_instance_vars_task = self.bot.loop.create_task(self._get_instance_vars())
        self._get_instance_vars_event = asyncio.Event()

    async def _get_instance_vars(self) -> None:
        """Get instance variables after they're available to get from the guild."""
        await self.bot.wait_until_guild_available()
        guild = self.bot.get_guild(Guild.id)
        self._verified_role = guild.get_role(Roles.verified)
        self._mod_alerts_channel = self.bot.get_channel(Channels.mod_alerts)
        self._mod_log_channel = self.bot.get_channel(Channels.mod_log)
        self.notifier = SilenceNotifier(self._mod_log_channel)
        self._get_instance_vars_event.set()

    @commands.command(aliases=("hush",))
    async def silence(self, ctx: Context, duration: HushDurationConverter = 10) -> None:
        """
        Silence the current channel for `duration` minutes or `forever`.

        Duration is capped at 15 minutes, passing forever makes the silence indefinite.
        Indefinitely silenced channels get added to a notifier which posts notices every 15 minutes from the start.
        """
        await self._get_instance_vars_event.wait()
        log.debug(f"{ctx.author} is silencing channel #{ctx.channel}.")
        if not await self._silence(ctx.channel, persistent=(duration is None), duration=duration):
            await ctx.send(f"{Emojis.cross_mark} current channel is already silenced.")
            return
        if duration is None:
            await ctx.send(f"{Emojis.check_mark} silenced current channel indefinitely.")
            return

        await ctx.send(f"{Emojis.check_mark} silenced current channel for {duration} minute(s).")
        await asyncio.sleep(duration*60)
        log.info(f"Unsilencing channel after set delay.")
        await ctx.invoke(self.unsilence)

    @commands.command(aliases=("unhush",))
    async def unsilence(self, ctx: Context) -> None:
        """
        Unsilence the current channel.

        If the channel was silenced indefinitely, notifications for the channel will stop.
        """
        await self._get_instance_vars_event.wait()
        log.debug(f"Unsilencing channel #{ctx.channel} from {ctx.author}'s command.")
        if await self._unsilence(ctx.channel):
            await ctx.send(f"{Emojis.check_mark} unsilenced current channel.")

    async def _silence(self, channel: TextChannel, persistent: bool, duration: Optional[int]) -> bool:
        """
        Silence `channel` for `self._verified_role`.

        If `persistent` is `True` add `channel` to notifier.
        `duration` is only used for logging; if None is passed `persistent` should be True to not log None.
        Return `True` if channel permissions were changed, `False` otherwise.
        """
        current_overwrite = channel.overwrites_for(self._verified_role)
        if current_overwrite.send_messages is False:
            log.info(f"Tried to silence channel #{channel} ({channel.id}) but the channel was already silenced.")
            return False
        await channel.set_permissions(self._verified_role, **dict(current_overwrite, send_messages=False))
        self.muted_channels.add(channel)
        if persistent:
            log.info(f"Silenced #{channel} ({channel.id}) indefinitely.")
            self.notifier.add_channel(channel)
            return True

        log.info(f"Silenced #{channel} ({channel.id}) for {duration} minute(s).")
        return True

    async def _unsilence(self, channel: TextChannel) -> bool:
        """
        Unsilence `channel`.

        Check if `channel` is silenced through a `PermissionOverwrite`,
        if it is unsilence it and remove it from the notifier.
        Return `True` if channel permissions were changed, `False` otherwise.
        """
        current_overwrite = channel.overwrites_for(self._verified_role)
        if current_overwrite.send_messages is False:
            await channel.set_permissions(self._verified_role, **dict(current_overwrite, send_messages=None))
            log.info(f"Unsilenced channel #{channel} ({channel.id}).")
            self.notifier.remove_channel(channel)
            self.muted_channels.discard(channel)
            return True
        log.info(f"Tried to unsilence channel #{channel} ({channel.id}) but the channel was not silenced.")
        return False

    def cog_unload(self) -> None:
        """Send alert with silenced channels on unload."""
        if self.muted_channels:
            channels_string = ''.join(channel.mention for channel in self.muted_channels)
            message = f"<@&{Roles.moderators}> channels left silenced on cog unload: {channels_string}"
            asyncio.create_task(self._mod_alerts_channel.send(message))

    # This cannot be static (must have a __func__ attribute).
    def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators to invoke the commands in this cog."""
        return with_role_check(ctx, *MODERATION_ROLES)
