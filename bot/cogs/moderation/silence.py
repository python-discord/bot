import asyncio
import json
import logging
from contextlib import suppress
from typing import Optional

from discord import TextChannel
from discord.ext import commands, tasks
from discord.ext.commands import Context

from bot.bot import Bot
from bot.constants import Channels, Emojis, Guild, MODERATION_ROLES, Roles
from bot.converters import HushDurationConverter
from bot.utils import RedisCache
from bot.utils.checks import with_role_check
from bot.utils.scheduling import Scheduler

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

    # Maps muted channel IDs to their previous overwrites for send_message and add_reactions.
    # Overwrites are stored as JSON.
    muted_channel_perms = RedisCache()

    def __init__(self, bot: Bot):
        self.bot = bot
        self.scheduler = Scheduler(self.__class__.__name__)

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

        self.scheduler.schedule_later(duration * 60, ctx.channel.id, ctx.invoke(self.unsilence))

    @commands.command(aliases=("unhush",))
    async def unsilence(self, ctx: Context) -> None:
        """
        Unsilence the current channel.

        If the channel was silenced indefinitely, notifications for the channel will stop.
        """
        await self._get_instance_vars_event.wait()
        log.debug(f"Unsilencing channel #{ctx.channel} from {ctx.author}'s command.")

        if not await self._unsilence(ctx.channel):
            overwrite = ctx.channel.overwrites_for(self._verified_role)
            if overwrite.send_messages is False and overwrite.add_reactions is False:
                await ctx.send(
                    f"{Emojis.cross_mark} current channel was not unsilenced because the current "
                    f"overwrites were set manually. Please edit them manually to unsilence."
                )
            else:
                await ctx.send(f"{Emojis.cross_mark} current channel was not silenced.")
        else:
            await ctx.send(f"{Emojis.check_mark} unsilenced current channel.")

    async def _silence(self, channel: TextChannel, persistent: bool, duration: Optional[int]) -> bool:
        """
        Silence `channel` for `self._verified_role`.

        If `persistent` is `True` add `channel` to notifier.
        `duration` is only used for logging; if None is passed `persistent` should be True to not log None.
        Return `True` if channel permissions were changed, `False` otherwise.
        """
        overwrite = channel.overwrites_for(self._verified_role)
        prev_overwrites = dict(send_messages=overwrite.send_messages, add_reactions=overwrite.add_reactions)

        if channel.id in self.scheduler or all(val is False for val in prev_overwrites.values()):
            log.info(f"Tried to silence channel #{channel} ({channel.id}) but the channel was already silenced.")
            return False

        overwrite.update(send_messages=False, add_reactions=False)
        await channel.set_permissions(self._verified_role, overwrite=overwrite)
        await self.muted_channel_perms.set(channel.id, json.dumps(prev_overwrites))

        if persistent:
            log.info(f"Silenced #{channel} ({channel.id}) indefinitely.")
            self.notifier.add_channel(channel)
            return True

        log.info(f"Silenced #{channel} ({channel.id}) for {duration} minute(s).")
        return True

    async def _unsilence(self, channel: TextChannel) -> bool:
        """
        Unsilence `channel`.

        If `channel` has a silence task scheduled or has its previous overwrites cached, unsilence
        it, cancel the task, and remove it from the notifier. Notify admins if it has a task but
        not cached overwrites.

        Return `True` if channel permissions were changed, `False` otherwise.
        """
        prev_overwrites = await self.muted_channel_perms.get(channel.id)
        if channel.id not in self.scheduler and prev_overwrites is None:
            log.info(f"Tried to unsilence channel #{channel} ({channel.id}) but the channel was not silenced.")
            return False

        overwrite = channel.overwrites_for(self._verified_role)
        if prev_overwrites is None:
            log.info(f"Missing previous overwrites for #{channel} ({channel.id}); defaulting to None.")
            overwrite.update(send_messages=None, add_reactions=None)
        else:
            overwrite.update(**json.loads(prev_overwrites))

        await channel.set_permissions(self._verified_role, overwrite=overwrite)
        log.info(f"Unsilenced channel #{channel} ({channel.id}).")

        self.scheduler.cancel(channel.id)
        self.notifier.remove_channel(channel)
        await self.muted_channel_perms.delete(channel.id)

        if prev_overwrites is None:
            await self._mod_alerts_channel.send(
                f"<@&{Roles.admins}> Restored overwrites with default values after unsilencing "
                f"{channel.mention}. Please check that the `Send Messages` and `Add Reactions` "
                f"overwrites for {self._verified_role.mention} are at their desired values."
            )

        return True

    def cog_unload(self) -> None:
        """Send alert with silenced channels and cancel scheduled tasks on unload."""
        self.scheduler.cancel_all()
        if self.muted_channel_perms:
            channels_string = ''.join(channel.mention for channel in self.muted_channel_perms)
            message = f"<@&{Roles.moderators}> channels left silenced on cog unload: {channels_string}"
            asyncio.create_task(self._mod_alerts_channel.send(message))

    # This cannot be static (must have a __func__ attribute).
    def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators to invoke the commands in this cog."""
        return with_role_check(ctx, *MODERATION_ROLES)
