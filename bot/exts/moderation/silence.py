import json
from collections import OrderedDict
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from async_rediscache import RedisCache
from discord import Guild, PermissionOverwrite, TextChannel, Thread, VoiceChannel
from discord.ext import commands, tasks
from discord.ext.commands import Context
from discord.utils import MISSING
from pydis_core.utils.scheduling import Scheduler

from bot import constants
from bot.bot import Bot
from bot.converters import HushDurationConverter
from bot.log import get_logger
from bot.utils.lock import LockedResourceError, lock, lock_arg

log = get_logger(__name__)

LOCK_NAMESPACE = "silence"

MSG_SILENCE_FAIL = f"{constants.Emojis.cross_mark} {{channel}} is already silenced."
MSG_SILENCE_PERMANENT = f"{constants.Emojis.check_mark} silenced {{channel}} indefinitely."
MSG_SILENCE_SUCCESS = f"{constants.Emojis.check_mark} silenced {{{{channel}}}} for {{duration}} minute(s)."

MSG_UNSILENCE_FAIL = f"{constants.Emojis.cross_mark} {{channel}} was not silenced."
MSG_UNSILENCE_MANUAL = (
    f"{constants.Emojis.cross_mark} {{channel}} was not unsilenced because the current overwrites were "
    f"set manually or the cache was prematurely cleared. "
    f"Please edit the overwrites manually to unsilence."
)
MSG_UNSILENCE_SUCCESS = f"{constants.Emojis.check_mark} unsilenced {{channel}}."

TextOrVoiceChannel = TextChannel | VoiceChannel

VOICE_CHANNELS = {
    constants.Channels.code_help_voice_0: constants.Channels.code_help_chat_0,
    constants.Channels.code_help_voice_1: constants.Channels.code_help_chat_1,
    constants.Channels.general_voice_0: constants.Channels.voice_chat_0,
    constants.Channels.general_voice_1: constants.Channels.voice_chat_1,
    constants.Channels.staff_voice: constants.Channels.staff_voice_chat,
}


class SilenceNotifier(tasks.Loop):
    """Loop notifier for posting notices to `alert_channel` containing added channels."""

    def __init__(self, alert_channel: TextChannel):
        super().__init__(
            self._notifier,
            seconds=1,
            minutes=0,
            hours=0,
            count=None,
            reconnect=True,
            time=MISSING,
            name=None
        )
        self._silenced_channels = {}
        self._alert_channel = alert_channel

    def add_channel(self, channel: TextOrVoiceChannel) -> None:
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
            channels_text = ", ".join(
                f"{channel.mention} for {(self._current_loop-start)//60} min"
                for channel, start in self._silenced_channels.items()
            )
            await self._alert_channel.send(
                f"<@&{constants.Roles.moderators}> currently silenced channels: {channels_text}"
            )


async def _select_lock_channel(args: OrderedDict[str, any]) -> TextOrVoiceChannel:
    """Passes the channel to be silenced to the resource lock."""
    channel, _ = Silence.parse_silence_args(args["ctx"], args["duration_or_channel"], args["duration"])
    return channel


class Silence(commands.Cog):
    """Commands for stopping channel messages for `everyone` role in a channel."""

    # Maps muted channel IDs to their previous overwrites for send_message and add_reactions.
    # Overwrites are stored as JSON.
    previous_overwrites = RedisCache()

    # Maps muted channel IDs to POSIX timestamps of when they'll be unsilenced.
    # A timestamp equal to -1 means it's indefinite.
    unsilence_timestamps = RedisCache()

    def __init__(self, bot: Bot):
        self.bot = bot
        self.scheduler = Scheduler(self.__class__.__name__)

    async def cog_load(self) -> None:
        """Set instance attributes once the guild is available and reschedule unsilences."""
        await self.bot.wait_until_guild_available()

        guild = self.bot.get_guild(constants.Guild.id)

        self._everyone_role = guild.default_role
        self._verified_voice_role = guild.get_role(constants.Roles.voice_verified)

        self._mod_alerts_channel = self.bot.get_channel(constants.Channels.mod_alerts)

        self.notifier = SilenceNotifier(self.bot.get_channel(constants.Channels.mod_log))
        await self._reschedule()

    async def send_message(
        self,
        message: str,
        source_channel: TextChannel,
        target_channel: TextOrVoiceChannel,
        *,
        alert_target: bool = False
    ) -> None:
        """Helper function to send message confirmation to `source_channel`, and notification to `target_channel`."""
        # Reply to invocation channel
        source_reply = message
        if source_channel != target_channel:
            source_reply = source_reply.format(channel=target_channel.mention)
        else:
            source_reply = source_reply.format(channel="current channel")
        await source_channel.send(source_reply)

        # Reply to target channel
        if alert_target:
            if isinstance(target_channel, VoiceChannel):
                voice_chat = self.bot.get_channel(VOICE_CHANNELS.get(target_channel.id))
                if voice_chat and source_channel != voice_chat:
                    await voice_chat.send(message.format(channel=target_channel.mention))

            elif source_channel != target_channel:
                await target_channel.send(message.format(channel="current channel"))

    @commands.command(aliases=("hush",))
    @lock(LOCK_NAMESPACE, _select_lock_channel, raise_error=True)
    async def silence(
        self,
        ctx: Context,
        duration_or_channel: TextOrVoiceChannel | HushDurationConverter = None,
        duration: HushDurationConverter = 10,
        *,
        kick: bool = False
    ) -> None:
        """
        Silence the current channel for `duration` minutes or `forever`.

        Duration is capped at 15 minutes, passing forever makes the silence indefinite.
        Indefinitely silenced channels get added to a notifier which posts notices every 15 minutes from the start.

        Passing a voice channel will attempt to move members out of the channel and back to force sync permissions.
        If `kick` is True, members will not be added back to the voice channel, and members will be unable to rejoin.
        """
        channel, duration = self.parse_silence_args(ctx, duration_or_channel, duration)

        channel_info = f"#{channel} ({channel.id})"
        log.debug(f"{ctx.author} is silencing channel {channel_info}.")

        # Since threads don't have specific overrides, we cannot silence them individually.
        # The parent channel has to be muted or the thread should be archived.
        if isinstance(channel, Thread):
            await ctx.send(":x: Threads cannot be silenced.")
            return

        if not await self._set_silence_overwrites(channel, kick=kick):
            log.info(f"Tried to silence channel {channel_info} but the channel was already silenced.")
            await self.send_message(MSG_SILENCE_FAIL, ctx.channel, channel, alert_target=False)
            return

        if isinstance(channel, VoiceChannel):
            if kick:
                await self._kick_voice_members(channel)
            else:
                await self._force_voice_sync(channel)

        await self._schedule_unsilence(ctx, channel, duration)

        if duration is None:
            self.notifier.add_channel(channel)
            log.info(f"Silenced {channel_info} indefinitely.")
            await self.send_message(MSG_SILENCE_PERMANENT, ctx.channel, channel, alert_target=True)

        else:
            log.info(f"Silenced {channel_info} for {duration} minute(s).")
            formatted_message = MSG_SILENCE_SUCCESS.format(duration=duration)
            await self.send_message(formatted_message, ctx.channel, channel, alert_target=True)

    @staticmethod
    def parse_silence_args(
        ctx: Context,
        duration_or_channel: TextOrVoiceChannel | int,
        duration: HushDurationConverter
    ) -> tuple[TextOrVoiceChannel, int | None]:
        """Helper method to parse the arguments of the silence command."""
        if duration_or_channel:
            if isinstance(duration_or_channel, TextChannel | VoiceChannel):
                channel = duration_or_channel
            else:
                channel = ctx.channel
                duration = duration_or_channel
        else:
            channel = ctx.channel

        if duration == -1:
            duration = None

        return channel, duration

    async def _set_silence_overwrites(self, channel: TextOrVoiceChannel, *, kick: bool = False) -> bool:
        """Set silence permission overwrites for `channel` and return True if successful."""
        # Get the original channel overwrites
        if isinstance(channel, TextChannel):
            role = self._everyone_role
            overwrite = channel.overwrites_for(role)
            prev_overwrites = dict(
                send_messages=overwrite.send_messages,
                add_reactions=overwrite.add_reactions,
                create_private_threads=overwrite.create_private_threads,
                create_public_threads=overwrite.create_public_threads,
                send_messages_in_threads=overwrite.send_messages_in_threads
            )

        else:
            role = self._verified_voice_role
            overwrite = channel.overwrites_for(role)
            prev_overwrites = dict(speak=overwrite.speak)
            if kick:
                prev_overwrites.update(connect=overwrite.connect)

        # Stop if channel was already silenced
        if channel.id in self.scheduler or all(val is False for val in prev_overwrites.values()):
            return False

        # Set new permissions, store
        overwrite.update(**dict.fromkeys(prev_overwrites, False))
        await channel.set_permissions(role, overwrite=overwrite)
        await self.previous_overwrites.set(channel.id, json.dumps(prev_overwrites))

        return True

    async def _schedule_unsilence(self, ctx: Context, channel: TextOrVoiceChannel, duration: int | None) -> None:
        """Schedule `ctx.channel` to be unsilenced if `duration` is not None."""
        if duration is None:
            await self.unsilence_timestamps.set(channel.id, -1)
        else:
            self.scheduler.schedule_later(duration * 60, channel.id, ctx.invoke(self.unsilence, channel=channel))
            unsilence_time = datetime.now(tz=UTC) + timedelta(minutes=duration)
            await self.unsilence_timestamps.set(channel.id, unsilence_time.timestamp())

    @commands.command(aliases=("unhush",))
    async def unsilence(self, ctx: Context, *, channel: TextOrVoiceChannel = None) -> None:
        """
        Unsilence the given channel if given, else the current one.

        If the channel was silenced indefinitely, notifications for the channel will stop.
        """
        if channel is None:
            channel = ctx.channel
        log.debug(f"Unsilencing channel #{channel} from {ctx.author}'s command.")
        await self._unsilence_wrapper(channel, ctx)

    @lock_arg(LOCK_NAMESPACE, "channel", raise_error=True)
    async def _unsilence_wrapper(self, channel: TextOrVoiceChannel, ctx: Context | None = None) -> None:
        """
        Unsilence `channel` and send a success/failure message to ctx.channel.

        If ctx is None or not passed, `channel` is used in its place.
        If `channel` and ctx.channel are the same, only one message is sent.
        """
        msg_channel = channel
        if ctx is not None:
            msg_channel = ctx.channel

        if not await self._unsilence(channel):
            if isinstance(channel, VoiceChannel):
                overwrite = channel.overwrites_for(self._verified_voice_role)
                has_channel_overwrites = overwrite.speak is False
            else:
                overwrite = channel.overwrites_for(self._everyone_role)
                has_channel_overwrites = overwrite.send_messages is False or overwrite.add_reactions is False

            # Send fail message to muted channel or voice chat channel, and invocation channel
            if has_channel_overwrites:
                await self.send_message(MSG_UNSILENCE_MANUAL, msg_channel, channel, alert_target=False)
            else:
                await self.send_message(MSG_UNSILENCE_FAIL, msg_channel, channel, alert_target=False)

        else:
            await self.send_message(MSG_UNSILENCE_SUCCESS, msg_channel, channel, alert_target=True)

    async def _unsilence(self, channel: TextOrVoiceChannel) -> bool:
        """
        Unsilence `channel`.

        If `channel` has a silence task scheduled or has its previous overwrites cached, unsilence
        it, cancel the task, and remove it from the notifier. Notify admins if it has a task but
        not cached overwrites.

        Return `True` if channel permissions were changed, `False` otherwise.
        """
        # Get stored overwrites, and return if channel is unsilenced
        prev_overwrites = await self.previous_overwrites.get(channel.id)
        if channel.id not in self.scheduler and prev_overwrites is None:
            log.info(f"Tried to unsilence channel #{channel} ({channel.id}) but the channel was not silenced.")
            return False

        # Select the role based on channel type, and get current overwrites
        if isinstance(channel, TextChannel):
            role = self._everyone_role
            overwrite = channel.overwrites_for(role)
            permissions = "`Send Messages` and `Add Reactions`"
        else:
            role = self._verified_voice_role
            overwrite = channel.overwrites_for(role)
            permissions = "`Speak` and `Connect`"

        # Check if old overwrites were not stored
        if prev_overwrites is None:
            log.info(f"Missing previous overwrites for #{channel} ({channel.id}); defaulting to None.")
            overwrite.update(
                send_messages=None,
                add_reactions=None,
                create_private_threads=None,
                create_public_threads=None,
                send_messages_in_threads=None,
                speak=None,
                connect=None
            )
        else:
            overwrite.update(**json.loads(prev_overwrites))

        # Update Permissions
        await channel.set_permissions(role, overwrite=overwrite)
        if isinstance(channel, VoiceChannel):
            await self._force_voice_sync(channel)

        log.info(f"Unsilenced channel #{channel} ({channel.id}).")

        self.scheduler.cancel(channel.id)
        self.notifier.remove_channel(channel)
        await self.previous_overwrites.delete(channel.id)
        await self.unsilence_timestamps.delete(channel.id)

        # Alert Admin team if old overwrites were not available
        if prev_overwrites is None:
            await self._mod_alerts_channel.send(
                f"<@&{constants.Roles.admins}> Restored overwrites with default values after unsilencing "
                f"{channel.mention}. Please check that the {permissions} "
                f"overwrites for {role.mention} are at their desired values."
            )

        return True

    @staticmethod
    async def _get_afk_channel(guild: Guild) -> VoiceChannel:
        """Get a guild's AFK channel, or create one if it does not exist."""
        afk_channel = guild.afk_channel

        if afk_channel is None:
            overwrites = {
                guild.default_role: PermissionOverwrite(speak=False, connect=False, view_channel=False)
            }
            afk_channel = await guild.create_voice_channel("mute-temp", overwrites=overwrites)
            log.info(f"Failed to get afk-channel, created #{afk_channel} ({afk_channel.id})")

        return afk_channel

    @staticmethod
    async def _kick_voice_members(channel: VoiceChannel) -> None:
        """Remove all non-staff members from a voice channel."""
        log.debug(f"Removing all non staff members from #{channel.name} ({channel.id}).")

        for member in channel.members:
            # Skip staff
            if any(role.id in constants.MODERATION_ROLES for role in member.roles):
                continue

            try:
                await member.move_to(None, reason="Kicking member from voice channel.")
                log.trace(f"Kicked {member.name} from voice channel.")
            except Exception as e:
                log.debug(f"Failed to move {member.name}. Reason: {e}")
                continue

        log.debug("Removed all members.")

    async def _force_voice_sync(self, channel: VoiceChannel) -> None:
        """
        Move all non-staff members from `channel` to a temporary channel and back to force toggle role mute.

        Permission modification has to happen before this function.
        """
        # Obtain temporary channel
        delete_channel = channel.guild.afk_channel is None
        afk_channel = await self._get_afk_channel(channel.guild)

        try:
            # Move all members to temporary channel and back
            for member in channel.members:
                # Skip staff
                if any(role.id in constants.MODERATION_ROLES for role in member.roles):
                    continue

                try:
                    await member.move_to(afk_channel, reason="Muting VC member.")
                    log.trace(f"Moved {member.name} to afk channel.")

                    await member.move_to(channel, reason="Muting VC member.")
                    log.trace(f"Moved {member.name} to original voice channel.")
                except Exception as e:
                    log.debug(f"Failed to move {member.name}. Reason: {e}")
                    continue

        finally:
            # Delete VC channel if it was created.
            if delete_channel:
                await afk_channel.delete(reason="Deleting temporary mute channel.")

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

            dt = datetime.fromtimestamp(timestamp, tz=UTC)
            delta = (dt - datetime.now(tz=UTC)).total_seconds()
            if delta <= 0:
                # Suppress the error since it's not being invoked by a user via the command.
                with suppress(LockedResourceError):
                    await self._unsilence_wrapper(channel)
            else:
                log.info(f"Rescheduling silence for #{channel} ({channel.id}).")
                self.scheduler.schedule_later(delta, channel_id, self._unsilence_wrapper(channel))

    # This cannot be static (must have a __func__ attribute).
    async def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators to invoke the commands in this cog."""
        return await commands.has_any_role(*constants.MODERATION_ROLES).predicate(ctx)

    async def cog_unload(self) -> None:
        """Cancel all scheduled tasks."""
        self.scheduler.cancel_all()


async def setup(bot: Bot) -> None:
    """Load the Silence cog."""
    await bot.add_cog(Silence(bot))
