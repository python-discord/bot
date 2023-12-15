import asyncio
from contextlib import suppress
from datetime import timedelta

import arrow
import discord
from async_rediscache import RedisCache
from discord import Colour, Member, TextChannel, VoiceState
from discord.ext.commands import Cog, Context, command, has_any_role
from pydis_core.site_api import ResponseCodeError

from bot.bot import Bot
from bot.constants import Bot as BotConfig, Channels, MODERATION_ROLES, Roles, VoiceGate as GateConf
from bot.decorators import has_no_roles, in_whitelist
from bot.exts.moderation.modlog import ModLog
from bot.log import get_logger
from bot.utils.checks import InWhitelistCheckFailure

log = get_logger(__name__)

# Flag written to the cog's RedisCache as a value when the Member's (key) notification
# was already removed ~ this signals both that no further notifications should be sent,
# and that the notification does not need to be removed. The implementation relies on
# this being falsey!
NO_MSG = 0

FAILED_MESSAGE = (
    """You are not currently eligible to use voice inside Python Discord for the following reasons:\n\n{reasons}"""
)

MESSAGE_FIELD_MAP = {
    "joined_at": f"have been on the server for less than {GateConf.minimum_days_member} days",
    "voice_gate_blocked": "have an active voice infraction",
    "total_messages": f"have sent less than {GateConf.minimum_messages} messages",
    "activity_blocks": f"have been active for fewer than {GateConf.minimum_activity_blocks} ten-minute blocks",
}

VOICE_PING = (
    "Wondering why you can't talk in the voice channels? "
    f"Use the `{BotConfig.prefix}voiceverify` command in here to verify. "
    "If you don't yet qualify, you'll be told why!"
)

VOICE_PING_DM = (
    "Wondering why you can't talk in the voice channels? "
    f"Use the `{BotConfig.prefix}voiceverify` command in "
    "{channel_mention} to verify. If you don't yet qualify, you'll be told why!"
)


class VerifyView(discord.ui.View):
    """Persistent view to add a Voice Verify button."""

    def __init__(self, bot: Bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Voice Verify", style=discord.ButtonStyle.primary, custom_id="voice_verify_button",)
    async def voice_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """A button that checks to see if the user qualifies for voice verification and verifies them if they do."""
        try:
            data = await self.bot.api_client.get(
                f"bot/users/{interaction.user.id}/metricity_data",
                raise_for_status=True
            )
        except ResponseCodeError as err:
            if err.response.status == 404:
                await interaction.response.send_message((
                    "We were unable to find user data for you. "
                    "Please try again shortly. "
                    "If this problem persists, please contact the server staff through ModMail."),
                    ephemeral=True,
                    delete_after=15,
                )
                log.info(f"Unable to find Metricity data about {interaction.user} ({interaction.user.id})")
            else:
                await interaction.response.send_message((
                    "We encountered an error while attempting to find data for your user. "
                    "Please try again and let us know if the problem persists."),
                    ephemeral=True,
                    delete_after=15,
                )
                log.warning(f"Got response code {err.status} while trying to get {interaction.user.id} Metricity data.")
            return

        checks = {
            "joined_at": (
                interaction.user.joined_at > arrow.utcnow() - timedelta(days=GateConf.minimum_days_member)
            ),
            "total_messages": data["total_messages"] < GateConf.minimum_messages,
            "voice_gate_blocked": data["voice_gate_blocked"],
            "activity_blocks": data["activity_blocks"] < GateConf.minimum_activity_blocks,
        }

        failed = any(checks.values())
        failed_reasons = [MESSAGE_FIELD_MAP[key] for key, value in checks.items() if value is True]
        for key, value in checks.items():
            if value:
                self.bot.stats.incr(f"voice_gate.failed.{key}")

        if failed:
            embed = discord.Embed(
                title="Voice Gate failed",
                description=FAILED_MESSAGE.format(reasons="\n".join(f"• You {reason}." for reason in failed_reasons)),
                color=Colour.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="Voice gate passed",
            description="You have been granted permission to use voice channels in Python Discord.",
            color=Colour.green()
        )

        if interaction.user.voice:
            embed.description += "\n\nPlease reconnect to your voice channel to be granted your new permissions."

        await interaction.response.send_message(embed=embed, ephemeral=True)
        await interaction.user.add_roles(discord.Object(Roles.voice_verified), reason="Voice Gate passed")
        self.bot.stats.incr("voice_gate.passed")


class VoiceGate(Cog):
    """Voice channels verification management."""

    # RedisCache[discord.User.id | discord.Member.id, discord.Message.id | int]
    # The cache's keys are the IDs of members who are verified or have joined a voice channel
    # The cache's values are either the message ID of the ping message or 0 (NO_MSG) if no message is present
    redis_cache = RedisCache()

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Adds verify button to be monitored by the bot."""
        self.bot.add_view(VerifyView(self.bot))

    @property
    def mod_log(self) -> ModLog:
        """Get the currently loaded ModLog cog instance."""
        return self.bot.get_cog("ModLog")

    @redis_cache.atomic_transaction  # Fully process each call until starting the next
    async def _delete_ping(self, member_id: int) -> None:
        """
        If `redis_cache` holds a message ID for `member_id`, delete the message.

        If the message was deleted, the value under the `member_id` key is then set to `NO_MSG`.
        When `member_id` is not in the cache, or has a value of `NO_MSG` already, this function
        does nothing.
        """
        if message_id := await self.redis_cache.get(member_id):
            log.trace(f"Removing voice gate reminder message for user: {member_id}")
            with suppress(discord.NotFound):
                await self.bot.http.delete_message(Channels.voice_gate, message_id)
            await self.redis_cache.set(member_id, NO_MSG)
        else:
            log.trace(f"Voice gate reminder message for user {member_id} was already removed")

    @redis_cache.atomic_transaction
    async def _ping_newcomer(self, member: discord.Member) -> tuple:
        """
        See if `member` should be sent a voice verification notification, and send it if so.

        Returns (False, None) if the notification was not sent. This happens when:
        * The `member` has already received the notification
        * The `member` is already voice-verified

        Otherwise, the notification message ID is stored in `redis_cache` and return (True, channel).
        channel is either [discord.TextChannel, discord.DMChannel].
        """
        if await self.redis_cache.contains(member.id):
            log.trace("User already in cache. Ignore.")
            return False, None

        log.trace("User not in cache and is in a voice channel.")
        verified = any(Roles.voice_verified == role.id for role in member.roles)
        if verified:
            log.trace("User is verified, add to the cache and ignore.")
            await self.redis_cache.set(member.id, NO_MSG)
            return False, None

        log.trace("User is unverified. Send ping.")

        await self.bot.wait_until_guild_available()
        voice_verification_channel = self.bot.get_channel(Channels.voice_gate)

        try:
            message = await member.send(VOICE_PING_DM.format(channel_mention=voice_verification_channel.mention))
        except discord.Forbidden:
            log.trace("DM failed for Voice ping message. Sending in channel.")
            message = await voice_verification_channel.send(f"Hello, {member.mention}! {VOICE_PING}")

        await self.redis_cache.set(member.id, message.id)
        return True, message.channel

    @Cog.listener()
    async def on_voice_state_update(self, member: Member, before: VoiceState, after: VoiceState) -> None:
        """Pings a user if they've never joined the voice chat before and aren't voice verified."""
        if member.bot:
            log.trace("User is a bot. Ignore.")
            return

        # member.voice will return None if the user is not in a voice channel
        if member.voice is None:
            log.trace("User not in a voice channel. Ignore.")
            return

        if isinstance(after.channel, discord.StageChannel):
            log.trace("User joined a stage channel. Ignore.")
            return

        # To avoid race conditions, checking if the user should receive a notification
        # and sending it if appropriate is delegated to an atomic helper
        notification_sent, message_channel = await self._ping_newcomer(member)

        # Schedule the channel ping notification to be deleted after the configured delay, which is
        # again delegated to an atomic helper
        if notification_sent and isinstance(message_channel, discord.TextChannel):
            await asyncio.sleep(GateConf.voice_ping_delete_delay)
            await self._delete_ping(member.id)

    async def cog_command_error(self, ctx: Context, error: Exception) -> None:
        """Check for & ignore any InWhitelistCheckFailure."""
        if isinstance(error, InWhitelistCheckFailure):
            error.handled = True

    @command(name="prepare_voice")
    @has_any_role(*MODERATION_ROLES)
    async def prepare_voice_button(self, ctx: Context, channel: TextChannel | None, *, text: str) -> None:
        """Sends a message that includes the Voice Verify button. Should only need to be run once."""
        if channel is None:
            await ctx.send(text, view=VerifyView(self.bot))
        elif not channel.permissions_for(ctx.author).send_messages:
            await ctx.send("You don't have permission to send messages to that channel.")
        else:
            await channel.send(text, view=VerifyView(self.bot))


async def setup(bot: Bot) -> None:
    """Loads the VoiceGate cog."""
    await bot.add_cog(VoiceGate(bot))
