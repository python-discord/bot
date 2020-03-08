import asyncio
import logging
from contextlib import suppress
from typing import Optional

from discord import PermissionOverwrite, TextChannel
from discord.ext import commands, tasks
from discord.ext.commands import Context, TextChannelConverter

from bot.bot import Bot
from bot.constants import Channels, Emojis, Guild, MODERATION_ROLES, Roles
from bot.converters import HushDurationConverter
from bot.utils.checks import with_role_check

log = logging.getLogger(__name__)


class FirstHash(tuple):
    """Tuple with only first item used for hash and eq."""

    def __new__(cls, *args):
        """Construct tuple from `args`."""
        return super().__new__(cls, args)

    def __hash__(self):
        return hash((self[0],))

    def __eq__(self, other: "FirstHash"):
        return self[0] == other[0]


class Silence(commands.Cog):
    """Commands for stopping channel messages for `verified` role in a channel."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.loop_alert_channels = set()
        self.bot.loop.create_task(self._get_server_values())

    async def _get_server_values(self) -> None:
        """Fetch required internal values after they're available."""
        await self.bot.wait_until_guild_available()
        guild = self.bot.get_guild(Guild.id)
        self._verified_role = guild.get_role(Roles.verified)
        self._mod_alerts_channel = self.bot.get_channel(Channels.mod_alerts)
        self._mod_log_channel = self.bot.get_channel(Channels.mod_log)

    @commands.command(aliases=("hush",))
    async def silence(
            self,
            ctx: Context,
            duration: HushDurationConverter = 10,
            channel: TextChannelConverter = None
    ) -> None:
        """
        Silence `channel` for `duration` minutes or `"forever"`.

        If duration is forever, start a notifier loop that triggers every 15 minutes.
        """
        channel = channel or ctx.channel

        if not await self._silence(channel, persistent=(duration is None), duration=duration):
            await ctx.send(f"{Emojis.cross_mark} {channel.mention} is already silenced.")
            return
        if duration is None:
            await ctx.send(f"{Emojis.check_mark} Channel {channel.mention} silenced indefinitely.")
            return

        await ctx.send(f"{Emojis.check_mark} {channel.mention} silenced for {duration} minute(s).")
        await asyncio.sleep(duration*60)
        await ctx.invoke(self.unsilence, channel=channel)

    @commands.command(aliases=("unhush",))
    async def unsilence(self, ctx: Context, channel: TextChannelConverter = None) -> None:
        """
        Unsilence `channel`.

        Unsilence a previously silenced `channel` and remove it from indefinitely muted channels notice if applicable.
        """
        channel = channel or ctx.channel
        alert_channel = self._mod_log_channel if ctx.invoked_with == "hush" else ctx.channel

        if await self._unsilence(channel):
            await alert_channel.send(f"{Emojis.check_mark} Unsilenced {channel.mention}.")

    async def _silence(self, channel: TextChannel, persistent: bool, duration: Optional[int]) -> bool:
        """
        Silence `channel` for `self._verified_role`.

        If `persistent` is `True` add `channel` with current iteration of `self._notifier`
        to `self.self.loop_alert_channels` and attempt to start notifier.
        `duration` is only used for logging; if None is passed `persistent` should be True to not log None.
        """
        if channel.overwrites_for(self._verified_role).send_messages is False:
            log.debug(f"Tried to silence channel #{channel} ({channel.id}) but the channel was already silenced.")
            return False
        await channel.set_permissions(self._verified_role, overwrite=PermissionOverwrite(send_messages=False))
        if persistent:
            log.debug(f"Silenced #{channel} ({channel.id}) indefinitely.")
            self.loop_alert_channels.add(FirstHash(channel, self._notifier.current_loop))
            with suppress(RuntimeError):
                self._notifier.start()
            return True

        log.debug(f"Silenced #{channel} ({channel.id}) for {duration} minute(s).")
        return True

    async def _unsilence(self, channel: TextChannel) -> bool:
        """
        Unsilence `channel`.

        Check if `channel` is silenced through a `PermissionOverwrite`,
        if it is unsilence it, attempt to remove it from `self.loop_alert_channels`
        and if `self.loop_alert_channels` are left empty, stop the `self._notifier`
        """
        if channel.overwrites_for(self._verified_role).send_messages is False:
            await channel.set_permissions(self._verified_role, overwrite=None)
            log.debug(f"Unsilenced channel #{channel} ({channel.id}).")

            with suppress(KeyError):
                self.loop_alert_channels.remove(FirstHash(channel))
                if not self.loop_alert_channels:
                    self._notifier.cancel()
            return True
        log.debug(f"Tried to unsilence channel #{channel} ({channel.id}) but the channel was not silenced.")
        return False

    @tasks.loop()
    async def _notifier(self) -> None:
        """Post notice of permanently silenced channels to `mod_alerts` periodically."""
        # Wait for 15 minutes between notices with pause at start of loop.
        await asyncio.sleep(15*60)
        current_iter = self._notifier.current_loop+1
        channels_text = ', '.join(
            f"{channel.mention} for {current_iter-start} min"
            for channel, start in self.loop_alert_channels
        )
        channels_log_text = ', '.join(
            f'#{channel} ({channel.id})' for channel, _ in self.loop_alert_channels
        )
        log.debug(f"Sending notice with channels: {channels_log_text}")
        await self._mod_alerts_channel.send(f"<@&{Roles.moderators}> currently silenced channels: {channels_text}")

    @_notifier.before_loop
    async def _log_notifier_start(self) -> None:
        log.trace("Starting notifier loop.")

    @_notifier.after_loop
    async def _log_notifier_end(self) -> None:
        log.trace("Stopping notifier loop.")

    # This cannot be static (must have a __func__ attribute).
    def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators to invoke the commands in this cog."""
        return with_role_check(ctx, *MODERATION_ROLES)
