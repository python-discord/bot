from datetime import timedelta

import arrow
import discord
from async_rediscache import RedisCache
from discord import Colour, Member, TextChannel, VoiceState
from discord.ext.commands import Cog, Context, command, has_any_role
from pydis_core.site_api import ResponseCodeError
from pydis_core.utils.channel import get_or_fetch_channel

from bot.bot import Bot
from bot.constants import Channels, Icons, MODERATION_ROLES, Roles, VoiceGate as GateConf
from bot.log import get_logger
from bot.utils.checks import InWhitelistCheckFailure
from bot.utils.messages import format_user
from bot.utils.modlog import send_log_message

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
    "joined_at": f"been on the server for less than {GateConf.minimum_days_member} days",
    "voice_gate_blocked": "an active voice infraction",
    "total_messages": f"sent less than {GateConf.minimum_messages} messages",
    "activity_blocks": f"been active for fewer than {GateConf.minimum_activity_blocks} ten-minute blocks",
}

VOICE_PING = (
    "Wondering why you can't talk in the voice channels? "
    "Click the Voice Verify button above to verify. "
    "If you don't yet qualify, you'll be told why!"
)


class VoiceVerificationView(discord.ui.View):
    """Persistent view to add a Voice Verify button."""

    def __init__(self, bot: Bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Voice Verify", style=discord.ButtonStyle.primary, custom_id="voice_verify_button",)
    async def voice_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """A button that checks to see if the user qualifies for voice verification and verifies them if they do."""
        if interaction.user.get_role(Roles.voice_verified):
            await interaction.response.send_message((
                "You have already verified! "
                "If you have received this message in error, "
                "please send a message to the ModMail bot."),
                ephemeral=True,
                delete_after=GateConf.delete_after_delay,
            )
            return

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
                    delete_after=GateConf.delete_after_delay,
                )
                log.info("Unable to find Metricity data about %s (%s)", interaction.user, interaction.user.id)
            else:
                await interaction.response.send_message((
                    "We encountered an error while attempting to find data for your user. "
                    "Please try again and let us know if the problem persists."),
                    ephemeral=True,
                    delete_after=GateConf.delete_after_delay,
                )
                log.warning(
                    "Got response code %s while trying to get %s Metricity data.",
                    err.status,
                    interaction.user.id
                )
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

        if failed:
            failed_reasons = []
            for key, value in checks.items():
                if value is True:
                    failed_reasons.append(MESSAGE_FIELD_MAP[key])
                    self.bot.stats.incr(f"voice_gate.failed.{key}")

            embed = discord.Embed(
                title="Voice Gate failed",
                description=FAILED_MESSAGE.format(
                    reasons="\n".join(f"- You have {reason}." for reason in failed_reasons)
                ),
                color=Colour.red()
            )

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True,
                delete_after=GateConf.delete_after_delay,
            )

            log_reasons = "\n".join(f"- Has {reason}." for reason in failed_reasons)

            await send_log_message(
                self.bot,
                icon_url=Icons.defcon_denied,
                colour=Colour.red(),
                title="Voice gate failed",
                text=f"{format_user(interaction.user)} failed the voice gate.\n\n{log_reasons}",
                thumbnail=interaction.user.avatar,
                channel_id=Channels.voice_log,
            )

            return

        embed = discord.Embed(
            title="Voice gate passed",
            description="You have been granted permission to use voice channels in Python Discord.",
            color=Colour.green(),
        )

        # interaction.user.voice will return None if the user is not in a voice channel
        if interaction.user.voice:
            embed.description += "\n\nPlease reconnect to your voice channel to be granted your new permissions."

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
            delete_after=GateConf.delete_after_delay,
        )
        await interaction.user.add_roles(discord.Object(Roles.voice_verified), reason="Voice Gate passed")

        await send_log_message(
            self.bot,
            icon_url=Icons.defcon_unshutdown,
            colour=Colour.green(),
            title="Voice gate passed",
            text=f"{format_user(interaction.user)} passed the voice gate.",
            thumbnail=interaction.user.avatar,
            channel_id=Channels.voice_log,
        )

        self.bot.stats.incr("voice_gate.passed")


class VoiceGate(Cog):
    """Voice channels verification management."""

    # RedisCache[discord.User.id | discord.Member.id, discord.Message.id | int]
    # The cache's keys are the IDs of members who are verified or have joined a voice channel
    # The cache's values are set to 0, as we only need to track which users have connected before
    redis_cache = RedisCache()

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Adds verify button to be monitored by the bot."""
        self.bot.add_view(VoiceVerificationView(self.bot))

    @redis_cache.atomic_transaction
    async def _ping_newcomer(self, member: discord.Member) -> None:
        """See if `member` should be sent a voice verification notification, and send it if so."""
        log.trace("User is not verified. Checking cache.")
        if await self.redis_cache.contains(member.id):
            log.trace("User %s already in cache. Ignore.", member.id)
            return

        log.trace("User %s is unverified and has not been pinged before. Sending ping.", member.id)
        await self.bot.wait_until_guild_available()
        voice_verification_channel = await get_or_fetch_channel(self.bot, Channels.voice_gate)

        await voice_verification_channel.send(
            f"Hello, {member.mention}! {VOICE_PING}",
            delete_after=GateConf.delete_after_delay,
        )

        await self.redis_cache.set(member.id, NO_MSG)
        log.trace("User %s added to cache to not be pinged again.", member.id)

    @Cog.listener()
    async def on_voice_state_update(self, member: Member, before: VoiceState, after: VoiceState) -> None:
        """Pings a user if they've never joined the voice chat before and aren't voice verified."""
        if member.bot:
            log.trace("User %s is a bot. Ignore.", member.id)
            return

        if member.get_role(Roles.voice_verified):
            log.trace("User %s already verified. Ignore", member.id)
            return

        # member.voice will return None if the user is not in a voice channel
        if member.voice is None:
            log.trace("User %s not in a voice channel. Ignore.", member.id)
            return

        if isinstance(after.channel, discord.StageChannel):
            log.trace("User %s joined a stage channel. Ignore.", member.id)
            return

        # To avoid race conditions, checking if the user should receive a notification
        # and sending it if appropriate is delegated to an atomic helper
        await self._ping_newcomer(member)

    async def cog_command_error(self, ctx: Context, error: Exception) -> None:
        """Check for & ignore any InWhitelistCheckFailure."""
        if isinstance(error, InWhitelistCheckFailure):
            error.handled = True

    @command(name="prepare_voice")
    @has_any_role(*MODERATION_ROLES)
    async def prepare_voice_button(self, ctx: Context, channel: TextChannel | None, *, text: str) -> None:
        """Sends a message that includes the Voice Verify button. Should only need to be run once."""
        if channel is None:
            await ctx.send(text, view=VoiceVerificationView(self.bot))
        elif not channel.permissions_for(ctx.author).send_messages:
            await ctx.send("You don't have permission to send messages to that channel.")
        else:
            await channel.send(text, view=VoiceVerificationView(self.bot))


async def setup(bot: Bot) -> None:
    """Loads the VoiceGate cog."""
    await bot.add_cog(VoiceGate(bot))
