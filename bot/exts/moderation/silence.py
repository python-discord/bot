import json
import logging
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from operator import attrgetter
from typing import Optional, Union

from async_rediscache import RedisCache
from discord import Member, PermissionOverwrite, TextChannel, VoiceChannel
from discord.ext import commands, tasks
from discord.ext.commands import Context

from bot.bot import Bot
from bot.constants import Channels, Emojis, Guild, MODERATION_ROLES, Roles
from bot.converters import HushDurationConverter
from bot.utils.lock import LockedResourceError, lock_arg
from bot.utils.scheduling import Scheduler

log = logging.getLogger(__name__)

LOCK_NAMESPACE = "silence"

MSG_SILENCE_FAIL = f"{Emojis.cross_mark} current channel is already silenced."
MSG_SILENCE_PERMANENT = f"{Emojis.check_mark} silenced current channel indefinitely."
MSG_SILENCE_SUCCESS = f"{Emojis.check_mark} silenced current channel for {{duration}} minute(s)."

MSG_UNSILENCE_FAIL = f"{Emojis.cross_mark} current channel was not silenced."
MSG_UNSILENCE_MANUAL = (
    f"{Emojis.cross_mark} current channel was not unsilenced because the current overwrites were "
    f"set manually or the cache was prematurely cleared. "
    f"Please edit the overwrites manually to unsilence."
)
MSG_UNSILENCE_SUCCESS = f"{Emojis.check_mark} unsilenced current channel."


class SilenceNotifier(tasks.Loop):
    """Loop notifier for posting notices to `alert_channel` containing added channels."""

    def __init__(self, alert_channel: TextChannel):
        super().__init__(self._notifier, seconds=1, minutes=0, hours=0, count=None, reconnect=True, loop=None)
        self._silenced_channels = {}
        self._alert_channel = alert_channel

    def add_channel(self, channel: Union[TextChannel, VoiceChannel]) -> None:
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
    previous_overwrites = RedisCache()

    # Maps muted channel IDs to POSIX timestamps of when they'll be unsilenced.
    # A timestamp equal to -1 means it's indefinite.
    unsilence_timestamps = RedisCache()

    def __init__(self, bot: Bot):
        self.bot = bot
        self.scheduler = Scheduler(self.__class__.__name__)

        self._init_task = self.bot.loop.create_task(self._async_init())

    async def _async_init(self) -> None:
        """Set instance attributes once the guild is available and reschedule unsilences."""
        await self.bot.wait_until_guild_available()

        guild = self.bot.get_guild(Guild.id)

        self._verified_msg_role = guild.get_role(Roles.verified)
        self._verified_voice_role = guild.get_role(Roles.voice_verified)
        self._helper_role = guild.get_role(Roles.helpers)

        self._mod_alerts_channel = self.bot.get_channel(Channels.mod_alerts)

        self.notifier = SilenceNotifier(self.bot.get_channel(Channels.mod_log))
        await self._reschedule()

    async def _get_related_text_channel(self, channel: VoiceChannel) -> Optional[TextChannel]:
        """Returns the text channel related to a voice channel."""
        # TODO: Figure out a dynamic way of doing this
        channels = {
            "off-topic": Channels.voice_chat,
            "code/help 1": Channels.code_help_voice,
            "code/help 2": Channels.code_help_voice_2,
            "admin": Channels.admins_voice,
            "staff": Channels.staff_voice
        }
        for name in channels.keys():
            if name in channel.name.lower():
                return self.bot.get_channel(channels[name])

    async def send_message(
        self, message: str, source_channel: TextChannel, target_channel: Union[TextChannel, VoiceChannel],
        alert_target: bool = False
    ) -> None:
        """Helper function to send message confirmation to `source_channel`, and notification to `target_channel`."""
        # Get TextChannel connected to VoiceChannel if channel is of type voice
        voice_chat = None
        if isinstance(target_channel, VoiceChannel):
            voice_chat = await self._get_related_text_channel(target_channel)

        # Reply to invocation channel
        source_reply = message
        if source_channel != target_channel:
            source_reply = source_reply.replace("current channel", target_channel.mention)
        await source_channel.send(source_reply)

        # Reply to target channel
        if alert_target and source_channel != target_channel and source_channel != voice_chat:
            if isinstance(target_channel, VoiceChannel) and (voice_chat is not None or voice_chat != source_channel):
                await voice_chat.send(message.replace("current channel", target_channel.mention))

            else:
                await target_channel.send(message)

    @commands.command(aliases=("hush",))
    @lock_arg(LOCK_NAMESPACE, "ctx", attrgetter("channel"), raise_error=True)
    async def silence(
        self, ctx: Context, duration: HushDurationConverter = 10, kick: bool = False,
        *, channel: Union[TextChannel, VoiceChannel] = None
    ) -> None:
        """
        Silence the current channel for `duration` minutes or `forever`.

        Duration is capped at 15 minutes, passing forever makes the silence indefinite.
        Indefinitely silenced channels get added to a notifier which posts notices every 15 minutes from the start.

        Passing a voice channel will attempt to move members out of the channel and back to force sync permissions.
        If `kick` is True, members will not be added back to the voice channel, and members will be unable to rejoin.
        """
        await self._init_task
        if channel is None:
            channel = ctx.channel
        channel_info = f"#{channel} ({channel.id})"
        log.debug(f"{ctx.author} is silencing channel {channel_info}.")

        if not await self._set_silence_overwrites(channel, kick):
            log.info(f"Tried to silence channel {channel_info} but the channel was already silenced.")
            await self.send_message(MSG_SILENCE_FAIL, ctx.channel, channel)
            return

        await self._schedule_unsilence(ctx, channel, duration)

        if duration is None:
            self.notifier.add_channel(channel)
            log.info(f"Silenced {channel_info} indefinitely.")
            await self.send_message(MSG_SILENCE_PERMANENT, ctx.channel, channel, True)

        else:
            log.info(f"Silenced {channel_info} for {duration} minute(s).")
            await self.send_message(MSG_SILENCE_SUCCESS.format(duration=duration), ctx.channel, channel, True)

    @commands.command(aliases=("unhush",))
    async def unsilence(self, ctx: Context, *, channel: Union[TextChannel, VoiceChannel] = None) -> None:
        """
        Unsilence the given channel if given, else the current one.

        If the channel was silenced indefinitely, notifications for the channel will stop.
        """
        await self._init_task
        if channel is None:
            channel = ctx.channel
        log.debug(f"Unsilencing channel #{channel} from {ctx.author}'s command.")
        await self._unsilence_wrapper(channel, ctx)

    @lock_arg(LOCK_NAMESPACE, "channel", raise_error=True)
    async def _unsilence_wrapper(
        self, channel: Union[TextChannel, VoiceChannel], ctx: Optional[Context] = None
    ) -> None:
        """Unsilence `channel` and send a success/failure message."""
        msg_channel = channel
        if ctx is not None:
            msg_channel = ctx.channel

        if not await self._unsilence(channel):
            if isinstance(channel, VoiceChannel):
                overwrite = channel.overwrites_for(self._verified_voice_role)
                manual = overwrite.speak is False
            else:
                overwrite = channel.overwrites_for(self._verified_msg_role)
                manual = overwrite.send_messages is False or overwrite.add_reactions is False

            # Send fail message to muted channel or voice chat channel, and invocation channel
            if manual:
                await self.send_message(MSG_UNSILENCE_MANUAL, msg_channel, channel)
            else:
                await self.send_message(MSG_UNSILENCE_FAIL, msg_channel, channel)

        else:
            # Send success message to muted channel or voice chat channel, and invocation channel
            if isinstance(channel, VoiceChannel):
                await self._force_voice_sync(channel)

            await self.send_message(MSG_UNSILENCE_SUCCESS, msg_channel, channel, True)

    async def _set_silence_overwrites(self, channel: Union[TextChannel, VoiceChannel], kick: bool = False) -> bool:
        """Set silence permission overwrites for `channel` and return True if successful."""
        if isinstance(channel, TextChannel):
            overwrite = channel.overwrites_for(self._verified_msg_role)
            prev_overwrites = dict(send_messages=overwrite.send_messages, add_reactions=overwrite.add_reactions)
        else:
            overwrite = channel.overwrites_for(self._verified_voice_role)
            prev_overwrites = dict(speak=overwrite.speak)
            if kick:
                prev_overwrites.update(connect=overwrite.connect)

        if channel.id in self.scheduler or all(val is False for val in prev_overwrites.values()):
            return False

        if isinstance(channel, TextChannel):
            overwrite.update(send_messages=False, add_reactions=False)
            await channel.set_permissions(self._verified_msg_role, overwrite=overwrite)
        else:
            overwrite.update(speak=False)
            if kick:
                overwrite.update(connect=False)

            await channel.set_permissions(self._verified_voice_role, overwrite=overwrite)
            await self._force_voice_sync(channel, kick=kick)

        await self.previous_overwrites.set(channel.id, json.dumps(prev_overwrites))

        return True

    async def _force_voice_sync(
        self, channel: VoiceChannel, member: Optional[Member] = None, kick: bool = False
    ) -> None:
        """
        Move all non-staff members from `channel` to a temporary channel and back to force toggle role mute.

        If `member` is passed, the mute only occurs to that member.
        Permission modification has to happen before this function.

        If `kick_all` is True, members will not be added back to the voice channel.
        """
        # Handle member picking logic
        if member is not None:
            members = [member]
        else:
            members = channel.members

        # Handle kick logic
        if kick:
            for member in members:
                await member.move_to(None, reason="Kicking voice channel member.")

            log.debug(f"Kicked all members from #{channel.name} ({channel.id}).")
            return

        # Obtain temporary channel
        afk_channel = channel.guild.afk_channel
        if afk_channel is None:
            overwrites = {
                channel.guild.default_role: PermissionOverwrite(speak=False, connect=False, view_channel=False)
            }
            afk_channel = await channel.guild.create_voice_channel("mute-temp", overwrites=overwrites)
            log.info(f"Failed to get afk-channel, created temporary channel #{afk_channel} ({afk_channel.id})")

            # Schedule channel deletion in case function errors out
            self.scheduler.schedule_later(
                30, afk_channel.id, afk_channel.delete(reason="Deleting temp mute channel.")
            )

        # Move all members to temporary channel and back
        for member in members:
            # Skip staff
            if self._helper_role in member.roles:
                continue

            await member.move_to(afk_channel, reason="Muting member.")
            log.debug(f"Moved {member.name} to afk channel.")

            await member.move_to(channel, reason="Muting member.")
            log.debug(f"Moved {member.name} to original voice channel.")

    async def _schedule_unsilence(
            self, ctx: Context, channel: Union[TextChannel, VoiceChannel], duration: Optional[int]
    ) -> None:
        """Schedule `ctx.channel` to be unsilenced if `duration` is not None."""
        if duration is None:
            await self.unsilence_timestamps.set(channel.id, -1)
        else:
            self.scheduler.schedule_later(duration * 60, channel.id, ctx.invoke(self.unsilence, channel=channel))
            unsilence_time = datetime.now(tz=timezone.utc) + timedelta(minutes=duration)
            await self.unsilence_timestamps.set(channel.id, unsilence_time.timestamp())

    async def _unsilence(self, channel: Union[TextChannel, VoiceChannel]) -> bool:
        """
        Unsilence `channel`.

        If `channel` has a silence task scheduled or has its previous overwrites cached, unsilence
        it, cancel the task, and remove it from the notifier. Notify admins if it has a task but
        not cached overwrites.

        Return `True` if channel permissions were changed, `False` otherwise.
        """
        prev_overwrites = await self.previous_overwrites.get(channel.id)
        if channel.id not in self.scheduler and prev_overwrites is None:
            log.info(f"Tried to unsilence channel #{channel} ({channel.id}) but the channel was not silenced.")
            return False

        if isinstance(channel, TextChannel):
            overwrite = channel.overwrites_for(self._verified_msg_role)
        else:
            overwrite = channel.overwrites_for(self._verified_voice_role)

        if prev_overwrites is None:
            log.info(f"Missing previous overwrites for #{channel} ({channel.id}); defaulting to None.")
            overwrite.update(send_messages=None, add_reactions=None, speak=None)
        else:
            overwrite.update(**json.loads(prev_overwrites))

        if isinstance(channel, TextChannel):
            await channel.set_permissions(self._verified_msg_role, overwrite=overwrite)
        else:
            await channel.set_permissions(self._verified_voice_role, overwrite=overwrite)
        log.info(f"Unsilenced channel #{channel} ({channel.id}).")

        self.scheduler.cancel(channel.id)
        self.notifier.remove_channel(channel)
        await self.previous_overwrites.delete(channel.id)
        await self.unsilence_timestamps.delete(channel.id)

        if prev_overwrites is None:
            if isinstance(channel, TextChannel):
                await self._mod_alerts_channel.send(
                    f"<@&{Roles.admins}> Restored overwrites with default values after unsilencing "
                    f"{channel.mention}. Please check that the `Send Messages` and `Add Reactions` "
                    f"overwrites for {self._verified_msg_role.mention} are at their desired values."
                )
            else:
                await self._mod_alerts_channel.send(
                    f"<@&{Roles.admins}> Restored overwrites with default values after unsilencing "
                    f"{channel.mention}. Please check that the `Speak` "
                    f"overwrites for {self._verified_voice_role.mention} are at their desired values."
                )

        return True

    async def _reschedule(self) -> None:
        """Reschedule unsilencing of active silences and add permanent ones to the notifier."""
        for channel_id, timestamp in await self.unsilence_timestamps.items():
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                log.info(f"Can't reschedule silence for {channel_id}: channel not found.")
                continue

            if timestamp == -1:
                log.info(f"Adding permanent silence for #{channel} ({channel.id}) to the notifier.")
                self.notifier.add_channel(channel)
                continue

            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            delta = (dt - datetime.now(tz=timezone.utc)).total_seconds()
            if delta <= 0:
                # Suppress the error since it's not being invoked by a user via the command.
                with suppress(LockedResourceError):
                    await self._unsilence_wrapper(channel)
            else:
                log.info(f"Rescheduling silence for #{channel} ({channel.id}).")
                self.scheduler.schedule_later(delta, channel_id, self._unsilence_wrapper(channel))

    def cog_unload(self) -> None:
        """Cancel the init task and scheduled tasks."""
        # It's important to wait for _init_task (specifically for _reschedule) to be cancelled
        # before cancelling scheduled tasks. Otherwise, it's possible for _reschedule to schedule
        # more tasks after cancel_all has finished, despite _init_task.cancel being called first.
        # This is cause cancel() on its own doesn't block until the task is cancelled.
        self._init_task.cancel()
        self._init_task.add_done_callback(lambda _: self.scheduler.cancel_all())

    # This cannot be static (must have a __func__ attribute).
    async def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators to invoke the commands in this cog."""
        return await commands.has_any_role(*MODERATION_ROLES).predicate(ctx)


def setup(bot: Bot) -> None:
    """Load the Silence cog."""
    bot.add_cog(Silence(bot))
