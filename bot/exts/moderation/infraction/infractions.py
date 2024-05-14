import textwrap
import typing as t
from datetime import UTC, timedelta

import arrow
import discord
from dateutil.relativedelta import relativedelta
from discord import Member
from discord.ext import commands
from discord.ext.commands import Context, command
from pydis_core.utils.members import get_or_fetch_member

from bot import constants
from bot.bot import Bot
from bot.constants import Event
from bot.converters import Age, Duration, DurationOrExpiry, MemberOrUser, UnambiguousMemberOrUser
from bot.decorators import ensure_future_timestamp, respect_role_hierarchy
from bot.exts.moderation.infraction import _utils
from bot.exts.moderation.infraction._scheduler import InfractionScheduler
from bot.log import get_logger
from bot.utils.messages import format_user

log = get_logger(__name__)

if t.TYPE_CHECKING:
    from bot.exts.moderation.clean import Clean
    from bot.exts.moderation.infraction.management import ModManagement
    from bot.exts.moderation.watchchannels.bigbrother import BigBrother


# Comp ban
DISCORD_ARTICLE_URL = "https://support.discord.com/hc/en-us/articles"
LINK_PASSWORD = DISCORD_ARTICLE_URL + "/218410947-I-forgot-my-Password-Where-can-I-set-a-new-one"
LINK_2FA = DISCORD_ARTICLE_URL + "/219576828-Setting-up-Two-Factor-Authentication"
COMP_BAN_REASON = (
    "Your account has been used to send links to a phishing website. You have been automatically banned. "
    "If you are not aware of sending them, that means your account has been compromised.\n\n"

    f"Here is a guide from Discord on [how to change your password]({LINK_PASSWORD}).\n\n"

    f"We also highly recommend that you [enable 2 factor authentication on your account]({LINK_2FA}), "
    "for heightened security.\n\n"

    "Once you have changed your password, feel free to follow the instructions at the bottom of "
    "this message to appeal your ban."
)
COMP_BAN_DURATION = timedelta(days=4)


class Infractions(InfractionScheduler, commands.Cog):
    """Apply and pardon infractions on users for moderation purposes."""

    category = "Moderation"
    category_description = "Server moderation tools."

    def __init__(self, bot: Bot):
        super().__init__(bot, supported_infractions={"ban", "kick", "timeout", "note", "warning", "voice_mute"})

        self.category = "Moderation"
        self._voice_verified_role = discord.Object(constants.Roles.voice_verified)

    # region: Permanent infractions

    @command(aliases=("warning",))
    async def warn(self, ctx: Context, user: UnambiguousMemberOrUser, *, reason: str | None = None) -> None:
        """Warn a user for the given reason."""
        if not isinstance(user, Member):
            await ctx.send(":x: The user doesn't appear to be on the server.")
            return

        infraction = await _utils.post_infraction(ctx, user, "warning", reason, active=False)
        if infraction is None:
            return

        await self.apply_infraction(ctx, infraction, user)

    @command()
    async def kick(self, ctx: Context, user: UnambiguousMemberOrUser, *, reason: str | None = None) -> None:
        """Kick a user for the given reason."""
        if not isinstance(user, Member):
            await ctx.send(":x: The user doesn't appear to be on the server.")
            return

        await self.apply_kick(ctx, user, reason)

    @command()
    @ensure_future_timestamp(timestamp_arg=3)
    async def ban(
        self,
        ctx: Context,
        user: UnambiguousMemberOrUser,
        duration_or_expiry: DurationOrExpiry | None = None,
        *,
        reason: str | None = None
    ) -> None:
        """
        Permanently ban a `user` for the given `reason` and stop watching them with Big Brother.

        If a duration is specified, it temporarily bans the `user` for the given duration.
        Alternatively, an ISO 8601 timestamp representing the expiry time can be provided
        for `duration_or_expiry`.
        """
        await self.apply_ban(ctx, user, reason, duration_or_expiry=duration_or_expiry)

    @command(aliases=("cban", "purgeban", "pban"))
    @ensure_future_timestamp(timestamp_arg=3)
    async def cleanban(
        self,
        ctx: Context,
        user: UnambiguousMemberOrUser,
        duration: DurationOrExpiry | None = None,
        *,
        reason: str | None = None
    ) -> None:
        """
        Same as ban, but also cleans all their messages from the last hour.

        If duration is specified, it temporarily bans that user for the given duration.
        """
        clean_cog: Clean | None = self.bot.get_cog("Clean")
        if clean_cog is None:
            # If we can't get the clean cog, fall back to native purgeban.
            await self.apply_ban(ctx, user, reason, purge_days=1, duration_or_expiry=duration)
            return

        infraction = await self.apply_ban(ctx, user, reason, duration_or_expiry=duration)
        if not infraction or not infraction.get("id"):
            # Ban was unsuccessful, quit early.
            return

        # Calling commands directly skips discord.py's convertors, so we need to convert args manually.
        clean_time = await Age().convert(ctx, "1h")

        log_url = await clean_cog._clean_messages(
            ctx,
            users=[user],
            channels="*",
            first_limit=clean_time,
            attempt_delete_invocation=False,
        )
        if not log_url:
            # Cleaning failed, or there were no messages to clean, exit early.
            return

        infr_manage_cog: ModManagement | None = self.bot.get_cog("ModManagement")
        if infr_manage_cog is None:
            # If we can't get the mod management cog, don't bother appending the log.
            return

        # Overwrite the context's send function so infraction append
        # doesn't output the update infraction confirmation message.
        async def send(*args, **kwargs) -> None:
            pass
        ctx.send = send
        await infr_manage_cog.infraction_append(ctx, infraction, None, reason=f"[Clean log]({log_url})")

    @command()
    async def compban(self, ctx: Context, user: UnambiguousMemberOrUser) -> None:
        """Same as cleanban, but specifically with the ban reason and duration used for compromised accounts."""
        await self.cleanban(ctx, user, duration=(arrow.utcnow() + COMP_BAN_DURATION).datetime, reason=COMP_BAN_REASON)

    @command(aliases=("vban",))
    async def voiceban(self, ctx: Context) -> None:
        """
        NOT IMPLEMENTED.

        Permanently ban a user from joining voice channels.

        If duration is specified, it temporarily voice bans that user for the given duration.
        """
        await ctx.send(":x: This command is not yet implemented. Maybe you meant to use `voicemute`?")

    @command(aliases=("vmute",))
    @ensure_future_timestamp(timestamp_arg=3)
    async def voicemute(
        self,
        ctx: Context,
        user: UnambiguousMemberOrUser,
        duration: DurationOrExpiry | None = None,
        *,
        reason: str | None
    ) -> None:
        """
        Permanently mute user in voice channels.

        If duration is specified, it temporarily voice mutes that user for the given duration.
        """
        await self.apply_voice_mute(ctx, user, reason, duration_or_expiry=duration)

    # endregion
    # region: Temporary infractions

    @command(aliases=["mute", "tempmute"])
    @ensure_future_timestamp(timestamp_arg=3)
    async def timeout(
        self, ctx: Context,
        user: UnambiguousMemberOrUser,
        duration: DurationOrExpiry | None = None,
        *,
        reason: str | None = None
    ) -> None:
        """
        Timeout a user for the given reason and duration.

        A unit of time should be appended to the duration.
        Units (∗case-sensitive):
        \u2003`y` - years
        \u2003`m` - months∗
        \u2003`w` - weeks
        \u2003`d` - days
        \u2003`h` - hours
        \u2003`M` - minutes∗
        \u2003`s` - seconds

        Alternatively, an ISO 8601 timestamp can be provided for the duration.

        If no duration is given, a one-hour duration is used by default.
        """  # noqa: RUF002
        if not isinstance(user, Member):
            await ctx.send(":x: The user doesn't appear to be on the server.")
            return

        if duration is None:
            duration = await Duration().convert(ctx, "1h")
        else:
            capped, duration = _utils.cap_timeout_duration(duration)
            if capped:
                await _utils.notify_timeout_cap(self.bot, ctx, user)

        await self.apply_timeout(ctx, user, reason, duration_or_expiry=duration)

    @command(aliases=("tban",))
    @ensure_future_timestamp(timestamp_arg=3)
    async def tempban(
        self,
        ctx: Context,
        user: UnambiguousMemberOrUser,
        duration_or_expiry: DurationOrExpiry,
        *,
        reason: str | None = None
    ) -> None:
        """
        Temporarily ban a user for the given reason and duration.

        A unit of time should be appended to the duration.
        Units (∗case-sensitive):
        \u2003`y` - years
        \u2003`m` - months∗
        \u2003`w` - weeks
        \u2003`d` - days
        \u2003`h` - hours
        \u2003`M` - minutes∗
        \u2003`s` - seconds

        Alternatively, an ISO 8601 timestamp can be provided for the duration.
        """  # noqa: RUF002
        await self.apply_ban(ctx, user, reason, duration_or_expiry=duration_or_expiry)

    @command(aliases=("tempvban", "tvban"))
    async def tempvoiceban(self, ctx: Context) -> None:
        """
        NOT IMPLEMENTED.

        Temporarily voice bans that user for the given duration.
        """
        await ctx.send(":x: This command is not yet implemented. Maybe you meant to use `tempvoicemute`?")

    @command(aliases=("tempvmute", "tvmute"))
    @ensure_future_timestamp(timestamp_arg=3)
    async def tempvoicemute(
        self,
        ctx: Context,
        user: UnambiguousMemberOrUser,
        duration: DurationOrExpiry,
        *,
        reason: str | None
    ) -> None:
        """
        Temporarily voice mute a user for the given reason and duration.

        A unit of time should be appended to the duration.
        Units (∗case-sensitive):
        \u2003`y` - years
        \u2003`m` - months∗
        \u2003`w` - weeks
        \u2003`d` - days
        \u2003`h` - hours
        \u2003`M` - minutes∗
        \u2003`s` - seconds

        Alternatively, an ISO 8601 timestamp can be provided for the duration.
        """  # noqa: RUF002
        await self.apply_voice_mute(ctx, user, reason, duration_or_expiry=duration)

    # endregion
    # region: Permanent shadow infractions

    @command(hidden=True)
    async def note(self, ctx: Context, user: UnambiguousMemberOrUser, *, reason: str | None = None) -> None:
        """Create a private note for a user with the given reason without notifying the user."""
        infraction = await _utils.post_infraction(ctx, user, "note", reason, hidden=True, active=False)
        if infraction is None:
            return

        await self.apply_infraction(ctx, infraction, user)

    @command(hidden=True, aliases=["shadowban", "sban"])
    async def shadow_ban(self, ctx: Context, user: UnambiguousMemberOrUser, *, reason: str | None = None) -> None:
        """Permanently ban a user for the given reason without notifying the user."""
        await self.apply_ban(ctx, user, reason, hidden=True)

    # endregion
    # region: Temporary shadow infractions

    @command(hidden=True, aliases=["shadowtempban", "stempban", "stban"])
    @ensure_future_timestamp(timestamp_arg=3)
    async def shadow_tempban(
        self,
        ctx: Context,
        user: UnambiguousMemberOrUser,
        duration: DurationOrExpiry,
        *,
        reason: str | None = None
    ) -> None:
        """
        Temporarily ban a user for the given reason and duration without notifying the user.

        A unit of time should be appended to the duration.
        Units (∗case-sensitive):
        \u2003`y` - years
        \u2003`m` - months∗
        \u2003`w` - weeks
        \u2003`d` - days
        \u2003`h` - hours
        \u2003`M` - minutes∗
        \u2003`s` - seconds

        Alternatively, an ISO 8601 timestamp can be provided for the duration.
        """  # noqa: RUF002
        await self.apply_ban(ctx, user, reason, duration_or_expiry=duration, hidden=True)

    # endregion
    # region: Remove infractions (un- commands)

    @command(aliases=("unmute",))
    async def untimeout(
        self,
        ctx: Context,
        user: UnambiguousMemberOrUser,
        *,
        pardon_reason: str | None = None
    ) -> None:
        """Prematurely end the active timeout infraction for the user."""
        await self.pardon_infraction(ctx, "timeout", user, pardon_reason)

    @command()
    async def unban(self, ctx: Context, user: UnambiguousMemberOrUser, *, pardon_reason: str) -> None:
        """Prematurely end the active ban infraction for the user."""
        await self.pardon_infraction(ctx, "ban", user, pardon_reason)

    @command(aliases=("uvban",))
    async def unvoiceban(self, ctx: Context) -> None:
        """
        NOT IMPLEMENTED.

        Temporarily voice bans that user for the given duration.
        """
        await ctx.send(":x: This command is not yet implemented. Maybe you meant to use `unvoicemute`?")

    @command(aliases=("uvmute",))
    async def unvoicemute(
        self,
        ctx: Context,
        user: UnambiguousMemberOrUser,
        *,
        pardon_reason: str | None = None
    ) -> None:
        """Prematurely end the active voice mute infraction for the user."""
        await self.pardon_infraction(ctx, "voice_mute", user, pardon_reason)

    # endregion
    # region: Base apply functions

    @respect_role_hierarchy(member_arg=2)
    async def apply_timeout(self, ctx: Context, user: Member, reason: str | None, **kwargs) -> None:
        """Apply a timeout infraction with kwargs passed to `post_infraction`."""
        if isinstance(user, Member) and user.top_role >= ctx.me.top_role:
            await ctx.send(":x: I can't timeout users above or equal to me in the role hierarchy.")
            return

        if active := await _utils.get_active_infraction(ctx, user, "timeout", send_msg=False):
            if active["actor"] != self.bot.user.id:
                await _utils.send_active_infraction_message(ctx, active)
                return

            # Allow the current timeout attempt to override an automatically triggered timeout.
            log_text = await self.deactivate_infraction(active, notify=False)
            if "Failure" in log_text:
                await ctx.send(
                    f":x: can't override infraction **timeout** for {user.mention}: "
                    f"failed to deactivate. {log_text['Failure']}"
                )
                return

        infraction = await _utils.post_infraction(ctx, user, "timeout", reason, active=True, **kwargs)
        if infraction is None:
            return

        self.mod_log.ignore(Event.member_update, user.id)

        async def action() -> None:
            # Skip members that left the server
            if not isinstance(user, Member):
                return
            duration_or_expiry = kwargs["duration_or_expiry"]
            if isinstance(duration_or_expiry, relativedelta):
                duration_or_expiry += arrow.utcnow()

            await user.edit(timed_out_until=duration_or_expiry, reason=reason)

        await self.apply_infraction(ctx, infraction, user, action)

    @respect_role_hierarchy(member_arg=2)
    async def apply_kick(self, ctx: Context, user: Member, reason: str | None, **kwargs) -> None:
        """Apply a kick infraction with kwargs passed to `post_infraction`."""
        if user.top_role >= ctx.me.top_role:
            await ctx.send(":x: I can't kick users above or equal to me in the role hierarchy.")
            return

        infraction = await _utils.post_infraction(ctx, user, "kick", reason, active=False, **kwargs)
        if infraction is None:
            return

        self.mod_log.ignore(Event.member_remove, user.id)

        if reason:
            reason = textwrap.shorten(reason, width=512, placeholder="...")

        async def action() -> None:
            await user.kick(reason=reason)

        await self.apply_infraction(ctx, infraction, user, action)

    @respect_role_hierarchy(member_arg=2)
    async def apply_ban(
        self,
        ctx: Context,
        user: MemberOrUser,
        reason: str | None,
        purge_days: int | None = 0,
        **kwargs
    ) -> dict | None:
        """
        Apply a ban infraction with kwargs passed to `post_infraction`.

        Will also remove the banned user from the Big Brother watch list if applicable.
        """
        if isinstance(user, Member) and user.top_role >= ctx.me.top_role:
            await ctx.send(":x: I can't ban users above or equal to me in the role hierarchy.")
            return None

        if not await _utils.confirm_elevated_user_ban(ctx, user):
            return None

        # In the case of a permanent ban, we don't need get_active_infractions to tell us if one is active
        is_temporary = kwargs.get("duration_or_expiry") is not None
        active_infraction = await _utils.get_active_infraction(ctx, user, "ban", is_temporary)

        if active_infraction:
            if is_temporary:
                log.trace("Tempban ignored as it cannot overwrite an active ban.")
                return None

            if active_infraction.get("expires_at") is None:
                log.trace("Permaban already exists, notify.")
                await ctx.send(f":x: User is already permanently banned (#{active_infraction['id']}).")
            else:
                log.trace("Tempban exists, notify.")
                await ctx.send(
                    f":x: Can't permanently ban user with existing temporary ban (#{active_infraction['id']}). "
                )

            return None

        infraction = await _utils.post_infraction(ctx, user, "ban", reason, active=True, **kwargs)
        if infraction is None:
            return None

        infraction["purge"] = "purge " if purge_days else ""

        async def action() -> None:
            # Discord only supports ban reasons up to 512 characters in length.
            discord_reason = textwrap.shorten(reason or "", width=512, placeholder="...")
            await ctx.guild.ban(user, reason=discord_reason, delete_message_days=purge_days)

        self.mod_log.ignore(Event.member_remove, user.id)
        await self.apply_infraction(ctx, infraction, user, action)

        bb_cog: BigBrother | None = self.bot.get_cog("Big Brother")
        if infraction.get("expires_at") is not None:
            log.trace(f"Ban isn't permanent; user {user} won't be unwatched by Big Brother.")
        elif not bb_cog:
            log.error(f"Big Brother cog not loaded; perma-banned user {user} won't be unwatched.")
        else:
            log.trace(f"Big Brother cog loaded; attempting to unwatch perma-banned user {user}.")
            bb_reason = "User has been permanently banned from the server. Automatically removed."
            await bb_cog.apply_unwatch(ctx, user, bb_reason, send_message=False)

        return infraction

    @respect_role_hierarchy(member_arg=2)
    async def apply_voice_mute(self, ctx: Context, user: MemberOrUser, reason: str | None, **kwargs) -> None:
        """Apply a voice mute infraction with kwargs passed to `post_infraction`."""
        if await _utils.get_active_infraction(ctx, user, "voice_mute"):
            return

        infraction = await _utils.post_infraction(ctx, user, "voice_mute", reason, active=True, **kwargs)
        if infraction is None:
            return

        self.mod_log.ignore(Event.member_update, user.id)

        if reason:
            reason = textwrap.shorten(reason, width=512, placeholder="...")

        async def action() -> None:
            # Skip members that left the server
            if not isinstance(user, Member):
                return

            await user.move_to(None, reason="Disconnected from voice to apply voice mute.")
            await user.remove_roles(self._voice_verified_role, reason=reason)

        await self.apply_infraction(ctx, infraction, user, action)

    # endregion
    # region: Base pardon functions

    async def pardon_timeout(
        self,
        user_id: int,
        guild: discord.Guild,
        reason: str | None,
        *,
        notify: bool = True
    ) -> dict[str, str]:
        """Remove a user's timeout, optionally DM them a notification, and return a log dict."""
        user = await get_or_fetch_member(guild, user_id)
        log_text = {}

        if user:
            # Remove the timeout.
            self.mod_log.ignore(Event.member_update, user.id)
            if user.is_timed_out():  # Handle pardons via the command and any other obscure weirdness.
                log.trace(f"Manually pardoning timeout for user {user.id}")
                await user.edit(timed_out_until=None, reason=reason)

            if notify:
                # DM the user about the expiration.
                notified = await _utils.notify_pardon(
                    user=user,
                    title="Your timeout has ended",
                    content="You may now send messages in the server.",
                    icon_url=_utils.INFRACTION_ICONS["timeout"][1]
                )
                log_text["DM"] = "Sent" if notified else "**Failed**"

            log_text["Member"] = format_user(user)
        else:
            log.info(f"Failed to remove timeout from user {user_id}: user not found")
            log_text["Failure"] = "User was not found in the guild."

        return log_text

    async def pardon_ban(self, user_id: int, guild: discord.Guild, reason: str | None) -> dict[str, str]:
        """Remove a user's ban on the Discord guild and return a log dict."""
        user = discord.Object(user_id)
        log_text = {}

        self.mod_log.ignore(Event.member_unban, user_id)

        try:
            await guild.unban(user, reason=reason)
        except discord.NotFound:
            log.info(f"Failed to unban user {user_id}: no active ban found on Discord")
            log_text["Note"] = "No active ban found on Discord."

        return log_text

    async def pardon_voice_mute(
        self,
        user_id: int,
        guild: discord.Guild,
        *,
        notify: bool = True
    ) -> dict[str, str]:
        """Optionally DM the user a pardon notification and return a log dict."""
        user = await get_or_fetch_member(guild, user_id)
        log_text = {}

        if user:
            if notify:
                # DM user about infraction expiration
                notified = await _utils.notify_pardon(
                    user=user,
                    title="Voice mute ended",
                    content="You have been unmuted and can verify yourself again in the server.",
                    icon_url=_utils.INFRACTION_ICONS["voice_mute"][1]
                )
                log_text["DM"] = "Sent" if notified else "**Failed**"

            log_text["Member"] = format_user(user)
        else:
            log_text["Info"] = "User was not found in the guild."

        return log_text

    async def _pardon_action(self, infraction: _utils.Infraction, notify: bool) -> dict[str, str] | None:
        """
        Execute deactivation steps specific to the infraction's type and return a log dict.

        If `notify` is True, notify the user of the pardon via DM where applicable.
        If an infraction type is unsupported, return None instead.
        """
        guild = self.bot.get_guild(constants.Guild.id)
        user_id = infraction["user"]
        reason = f"Infraction #{infraction['id']} expired or was pardoned."

        if infraction["type"] == "timeout":
            return await self.pardon_timeout(user_id, guild, reason, notify=notify)
        if infraction["type"] == "ban":
            return await self.pardon_ban(user_id, guild, reason)
        if infraction["type"] == "voice_mute":
            return await self.pardon_voice_mute(user_id, guild, notify=notify)
        return None

    # endregion

    # This cannot be static (must have a __func__ attribute).
    async def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators to invoke the commands in this cog."""
        return await commands.has_any_role(*constants.MODERATION_ROLES).predicate(ctx)

    # This cannot be static (must have a __func__ attribute).
    async def cog_command_error(self, ctx: Context, error: Exception) -> None:
        """Send a notification to the invoking context on a Union failure."""
        if isinstance(error, commands.BadUnionArgument):
            if discord.User in error.converters or Member in error.converters:
                await ctx.send(str(error.errors[0]))
                error.handled = True

    @commands.Cog.listener()
    async def on_member_join(self, member: Member) -> None:
        """
        Apply active timeout infractions for returning members.

        This is needed for users who might have had their infraction edited in our database but not in Discord itself.
        """
        active_timeouts = await self.bot.api_client.get(
            endpoint="bot/infractions",
            params={"active": "true", "type": "timeout", "user__id": member.id}
        )

        if active_timeouts:
            timeout_infraction = active_timeouts[0]
            expiry = arrow.get(timeout_infraction["expires_at"], tzinfo=UTC).datetime.replace(second=0, microsecond=0)

            if member.is_timed_out() and expiry == member.timed_out_until.replace(second=0, microsecond=0):
                return

            reason = f"Applying active timeout for returning member: {timeout_infraction['id']}"

            async def action() -> None:
                await member.edit(timed_out_until=expiry, reason=reason)
            await self.reapply_infraction(timeout_infraction, action)


async def setup(bot: Bot) -> None:
    """Load the Infractions cog."""
    await bot.add_cog(Infractions(bot))
