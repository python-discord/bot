import logging
from contextlib import suppress
from datetime import datetime, timedelta

import discord
from dateutil import parser
from discord import Colour
from discord.ext.commands import Cog, Context, command

from bot.api import ResponseCodeError
from bot.bot import Bot
from bot.constants import Channels, Event, MODERATION_ROLES, Roles, VoiceGate as GateConf
from bot.decorators import has_no_roles, in_whitelist
from bot.exts.moderation.modlog import ModLog
from bot.utils.checks import InWhitelistCheckFailure

log = logging.getLogger(__name__)

FAILED_MESSAGE = """{user} you don't meet with our current requirements to pass Voice Gate. You {reasons}."""

MESSAGE_FIELD_MAP = {
    "verified_at": f"have been verified for less {GateConf.minimum_days_verified} days",
    "voice_banned": "have an active voice ban infraction",
    "total_messages": f"have sent less than {GateConf.minimum_messages} messages",
}


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
        # Send this as first thing in order to return after sending DM
        await ctx.send(f"{ctx.author.mention}, check your DMs.")

        try:
            data = await self.bot.api_client.get(f"bot/users/{ctx.author.id}/metricity_data")
        except ResponseCodeError as e:
            if e.status == 404:
                embed = discord.Embed(
                    title="Not found",
                    description=f"We were unable to find user data for you. Please try again shortly, if this problem persists please contact the server staff through Modmail.",
                    color=Colour.red()
                )
                log.info(f"Unable to find Metricity data about {ctx.author} ({ctx.author.id})")
            else:
                embed = discord.Embed(
                    title="Unexpected response",
                    description="We encountered an error while attempting to find data for your user. Please try again and let us know if the problem persists.",
                    color=Colour.red()
                )
                log.warning(f"Got response code {e.status} while trying to get {ctx.author.id} Metricity data.")

            await ctx.author.send(embed=embed)
            return

        # Pre-parse this for better code style
        if data["verified_at"] is not None:
            data["verified_at"] = parser.isoparse(data["verified_at"])
        else:
            data["verified_at"] = datetime.utcnow() - timedelta(days=3)

        checks = {
            "verified_at": data["verified_at"] > datetime.utcnow() - timedelta(days=GateConf.minimum_days_verified),
            "total_messages": data["total_messages"] < GateConf.minimum_messages,
            "voice_banned": data["voice_banned"]
        }
        failed = any(checks.values())
        failed_reasons = [MESSAGE_FIELD_MAP[key] for key, value in checks.items() if value is True]
        [self.bot.stats.incr(f"voice_gate.failed.{key}") for key, value in checks.items() if value is True]

        if failed:
            if len(failed_reasons) > 1:
                reasons = f"{', '.join(failed_reasons[:-1])} and {failed_reasons[-1]}"
            else:
                reasons = failed_reasons[0]

            embed = discord.Embed(
                title="Voice Gate not passed",
                description=FAILED_MESSAGE.format(user=ctx.author.mention, reasons=reasons),
                color=Colour.red()
            )
            await ctx.author.send(embed=embed)
            return

        self.mod_log.ignore(Event.member_update, ctx.author.id)
        await ctx.author.add_roles(discord.Object(Roles.voice_verified), reason="Voice Gate passed")
        embed = discord.Embed(
            title="Voice gate passed",
            description="You have been granted permission to use voice channels in Python Discord.",
            color=Colour.green()
        )
        await ctx.author.send(embed=embed)
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
                await message.delete(delay=GateConf.bot_message_delete_delay)
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
