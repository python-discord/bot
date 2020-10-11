import logging
from contextlib import suppress
from datetime import datetime, timedelta

import discord
from dateutil import parser
from discord.ext.commands import Cog, Context, command

from bot.api import ResponseCodeError
from bot.bot import Bot
from bot.constants import Channels, Event, MODERATION_ROLES, Roles, VoiceGate as VoiceGateConf
from bot.decorators import has_no_roles, in_whitelist
from bot.exts.moderation.modlog import ModLog
from bot.utils.checks import InWhitelistCheckFailure

log = logging.getLogger(__name__)

# Messages for case when user don't meet with requirements
NOT_ENOUGH_MESSAGES = f"haven't sent at least {VoiceGateConf.minimum_messages} messages"
NOT_ENOUGH_DAYS_AFTER_VERIFICATION = f"haven't been verified for at least {VoiceGateConf.minimum_days_verified} days"
VOICE_BANNED = "are voice banned"

FAILED_MESSAGE = """{user} you don't meet with our current requirements to pass Voice Gate. You {reasons}."""


class VoiceGate(Cog):
    """Voice channels verification management."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @property
    def mod_log(self) -> ModLog:
        """Get the currently loaded ModLog cog instance."""
        return self.bot.get_cog("ModLog")

    @command(aliases=('voiceverify', 'vverify', 'voicev', 'vv'))
    @has_no_roles(Roles.voice_verified)
    @in_whitelist(channels=(Channels.voice_gate,), redirect=None)
    async def voice_verify(self, ctx: Context, *_) -> None:
        """
        Apply to be able to use voice within the Discord server.

        In order to use voice you must meet all three of the following criteria:
        - You must have over a certain number of messages within the Discord server
        - You must have accepted our rules over a certain number of days ago
        - You must not be actively banned from using our voice channels
        """
        try:
            data = await self.bot.api_client.get(f"bot/users/{ctx.author.id}/metricity_data")
        except ResponseCodeError as e:
            if e.status == 404:
                await ctx.send(f":x: {ctx.author.mention} Unable to find Metricity data about you.")
                log.info(f"Unable to find Metricity data about {ctx.author} ({ctx.author.id})")
            else:
                log.warning(f"Got response code {e.status} while trying to get {ctx.author.id} metricity data.")
                await ctx.send(":x: Got unexpected response from site. Please let us know about this.")
            return

        # Pre-parse this for better code style
        data["verified_at"] = parser.isoparse(data["verified_at"])

        failed = False
        failed_reasons = []

        if data["verified_at"] > datetime.utcnow() - timedelta(days=VoiceGateConf.minimum_days_verified):
            failed_reasons.append(NOT_ENOUGH_DAYS_AFTER_VERIFICATION)
            failed = True
            self.bot.stats.incr("voice_gate.failed.verified_at")
        if data["total_messages"] < VoiceGateConf.minimum_messages:
            failed_reasons.append(NOT_ENOUGH_MESSAGES)
            failed = True
            self.bot.stats.incr("voice_gate.failed.total_messages")
        if data["voice_banned"]:
            failed_reasons.append(VOICE_BANNED)
            failed = True
            self.bot.stats.incr("voice_gate.failed.voice_banned")

        if failed:
            if len(failed_reasons) > 1:
                reasons = f"{', '.join(failed_reasons[:-1])} and {failed_reasons[-1]}"
            else:
                reasons = failed_reasons[0]

            await ctx.send(
                FAILED_MESSAGE.format(
                    user=ctx.author.mention,
                    reasons=reasons
                )
            )
            return

        self.mod_log.ignore(Event.member_update, ctx.author.id)
        await ctx.author.add_roles(discord.Object(Roles.voice_verified), reason="Voice Gate passed")
        await ctx.author.send(
            ":tada: Congratulations! You are now Voice Verified and have access to PyDis Voice Channels."
        )
        self.bot.stats.incr("voice_gate.passed")

    @Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Delete all non-staff messages from voice gate channel that don't invoke voice verify command."""
        # Check is channel voice gate
        if message.channel.id != Channels.voice_gate:
            return

        ctx = await self.bot.get_context(message)
        is_verify_command = ctx.command is not None and ctx.command.name == "voice_verify"

        # When it's bot sent message, delete it after some time
        if message.author.bot:
            with suppress(discord.NotFound):
                await message.delete(delay=VoiceGateConf.bot_message_delete_delay)
                return

        # Then check is member moderator+, because we don't want to delete their messages.
        if any(role.id in MODERATION_ROLES for role in message.author.roles) and is_verify_command is False:
            log.trace(f"Excluding moderator message {message.id} from deletion in #{message.channel}.")
            return

        # Ignore deleted voice verification messages
        if ctx.command is not None and ctx.command.name == "voice_verify":
            self.mod_log.ignore(Event.message_delete, message.id)

        with suppress(discord.NotFound):
            await message.delete()

    async def cog_command_error(self, ctx: Context, error: Exception) -> None:
        """Check for & ignore any InWhitelistCheckFailure."""
        if isinstance(error, InWhitelistCheckFailure):
            error.handled = True


def setup(bot: Bot) -> None:
    """Loads the VoiceGate cog."""
    bot.add_cog(VoiceGate(bot))
