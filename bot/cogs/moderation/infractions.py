import logging
import typing as t
from datetime import datetime

import dateutil.parser
import discord
from discord import Member
from discord.ext import commands
from discord.ext.commands import Context, command

from bot import constants
from bot.constants import Event
from bot.decorators import respect_role_hierarchy
from bot.utils.checks import with_role_check
from . import utils
from .scheduler import InfractionScheduler
from .utils import MemberObject

log = logging.getLogger(__name__)

MemberConverter = t.Union[utils.UserTypes, utils.proxy_user]


class Infractions(InfractionScheduler, commands.Cog):
    """Apply and pardon infractions on users for moderation purposes."""

    category = "Moderation"
    category_description = "Server moderation tools."

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)

        self.category = "Moderation"
        self._muted_role = discord.Object(constants.Roles.muted)

    @commands.Cog.listener()
    async def on_member_join(self, member: Member) -> None:
        """Reapply active mute infractions for returning members."""
        active_mutes = await self.bot.api_client.get(
            'bot/infractions',
            params={
                'user__id': str(member.id),
                'type': 'mute',
                'active': 'true'
            }
        )
        if not active_mutes:
            return

        # Assume a single mute because of restrictions elsewhere.
        mute = active_mutes[0]

        # Calculate the time remaining, in seconds, for the mute.
        expiry = dateutil.parser.isoparse(mute["expires_at"]).replace(tzinfo=None)
        delta = (expiry - datetime.utcnow()).total_seconds()

        # Mark as inactive if less than a minute remains.
        if delta < 60:
            await self.deactivate_infraction(mute)
            return

        # Allowing mod log since this is a passive action that should be logged.
        await member.add_roles(self._muted_role, reason=f"Re-applying active mute: {mute['id']}")
        log.debug(f"User {member.id} has been re-muted on rejoin.")

    # region: Permanent infractions

    @command()
    async def warn(self, ctx: Context, user: Member, *, reason: str = None) -> None:
        """Warn a user for the given reason."""
        infraction = await utils.post_infraction(ctx, user, "warning", reason, active=False)
        if infraction is None:
            return

        await self.apply_infraction(ctx, infraction, user)

    @command()
    async def kick(self, ctx: Context, user: Member, *, reason: str = None) -> None:
        """Kick a user for the given reason."""
        await self.apply_kick(ctx, user, reason, active=False)

    @command()
    async def ban(self, ctx: Context, user: MemberConverter, *, reason: str = None) -> None:
        """Permanently ban a user for the given reason."""
        await self.apply_ban(ctx, user, reason)

    # endregion
    # region: Temporary infractions

    @command(aliases=["mute"])
    async def tempmute(self, ctx: Context, user: Member, duration: utils.Expiry, *, reason: str = None) -> None:
        """
        Temporarily mute a user for the given reason and duration.

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
        """
        await self.apply_mute(ctx, user, reason, expires_at=duration)

    @command()
    async def tempban(self, ctx: Context, user: MemberConverter, duration: utils.Expiry, *, reason: str = None) -> None:
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
        """
        await self.apply_ban(ctx, user, reason, expires_at=duration)

    # endregion
    # region: Permanent shadow infractions

    @command(hidden=True)
    async def note(self, ctx: Context, user: MemberConverter, *, reason: str = None) -> None:
        """Create a private note for a user with the given reason without notifying the user."""
        infraction = await utils.post_infraction(ctx, user, "note", reason, hidden=True, active=False)
        if infraction is None:
            return

        await self.apply_infraction(ctx, infraction, user)

    @command(hidden=True, aliases=['shadowkick', 'skick'])
    async def shadow_kick(self, ctx: Context, user: Member, *, reason: str = None) -> None:
        """Kick a user for the given reason without notifying the user."""
        await self.apply_kick(ctx, user, reason, hidden=True, active=False)

    @command(hidden=True, aliases=['shadowban', 'sban'])
    async def shadow_ban(self, ctx: Context, user: MemberConverter, *, reason: str = None) -> None:
        """Permanently ban a user for the given reason without notifying the user."""
        await self.apply_ban(ctx, user, reason, hidden=True)

    # endregion
    # region: Temporary shadow infractions

    @command(hidden=True, aliases=["shadowtempmute, stempmute", "shadowmute", "smute"])
    async def shadow_tempmute(self, ctx: Context, user: Member, duration: utils.Expiry, *, reason: str = None) -> None:
        """
        Temporarily mute a user for the given reason and duration without notifying the user.

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
        """
        await self.apply_mute(ctx, user, reason, expires_at=duration, hidden=True)

    @command(hidden=True, aliases=["shadowtempban, stempban"])
    async def shadow_tempban(
        self,
        ctx: Context,
        user: MemberConverter,
        duration: utils.Expiry,
        *,
        reason: str = None
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
        """
        await self.apply_ban(ctx, user, reason, expires_at=duration, hidden=True)

    # endregion
    # region: Remove infractions (un- commands)

    @command()
    async def unmute(self, ctx: Context, user: MemberConverter) -> None:
        """Prematurely end the active mute infraction for the user."""
        await self.pardon_infraction(ctx, "mute", user)

    @command()
    async def unban(self, ctx: Context, user: MemberConverter) -> None:
        """Prematurely end the active ban infraction for the user."""
        await self.pardon_infraction(ctx, "ban", user)

    # endregion
    # region: Base infraction functions

    async def apply_mute(self, ctx: Context, user: Member, reason: str, **kwargs) -> None:
        """Apply a mute infraction with kwargs passed to `post_infraction`."""
        if await utils.has_active_infraction(ctx, user, "mute"):
            return

        infraction = await utils.post_infraction(ctx, user, "mute", reason, **kwargs)
        if infraction is None:
            return

        self.mod_log.ignore(Event.member_update, user.id)

        action = user.add_roles(self._muted_role, reason=reason)
        await self.apply_infraction(ctx, infraction, user, action)

    @respect_role_hierarchy()
    async def apply_kick(self, ctx: Context, user: Member, reason: str, **kwargs) -> None:
        """Apply a kick infraction with kwargs passed to `post_infraction`."""
        infraction = await utils.post_infraction(ctx, user, "kick", reason, **kwargs)
        if infraction is None:
            return

        self.mod_log.ignore(Event.member_remove, user.id)

        action = user.kick(reason=reason)
        await self.apply_infraction(ctx, infraction, user, action)

    @respect_role_hierarchy()
    async def apply_ban(self, ctx: Context, user: MemberObject, reason: str, **kwargs) -> None:
        """Apply a ban infraction with kwargs passed to `post_infraction`."""
        if await utils.has_active_infraction(ctx, user, "ban"):
            return

        infraction = await utils.post_infraction(ctx, user, "ban", reason, **kwargs)
        if infraction is None:
            return

        self.mod_log.ignore(Event.member_remove, user.id)

        action = ctx.guild.ban(user, reason=reason, delete_message_days=0)
        await self.apply_infraction(ctx, infraction, user, action)

    # endregion

    # This cannot be static (must have a __func__ attribute).
    def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators to invoke the commands in this cog."""
        return with_role_check(ctx, *constants.MODERATION_ROLES)

    # This cannot be static (must have a __func__ attribute).
    async def cog_command_error(self, ctx: Context, error: Exception) -> None:
        """Send a notification to the invoking context on a Union failure."""
        if isinstance(error, commands.BadUnionArgument):
            if discord.User in error.converters:
                await ctx.send(str(error.errors[0]))
                error.handled = True
