import datetime

import discord
from discord.ext import commands

from bot.bot import Bot
from bot.constants import Emojis, Roles, STAFF_ROLES, VideoPermission
from bot.converters import Expiry
from bot.utils.scheduling import Scheduler
from bot.utils.time import format_infraction_with_duration

# Constant error messages
USER_ALREADY_ALLOWED_TO_STREAM = f"{Emojis.cross_mark}This user can already stream."
USER_ALREADY_NOT_ALLOWED_TO_STREAM = f"{Emojis.cross_mark}This user already can't stream."


class Stream(commands.Cog):
    """Grant and revoke streaming permissions from users."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.scheduler = Scheduler(self.__class__.__name__)

    @staticmethod
    async def _remove_streaming_permission(schedule_user: discord.Member) -> None:
        """Remove streaming permission from Member."""
        await schedule_user.remove_roles(discord.Object(Roles.video), reason="Temporary streaming access revoked")

    @commands.command(aliases=("streaming",))
    @commands.has_any_role(*STAFF_ROLES)
    async def stream(
            self,
            ctx: commands.Context,
            user: discord.Member,
            duration: Expiry =
            datetime.datetime.utcnow() + datetime.timedelta(minutes=VideoPermission.default_permission_duration),
            *_
    ) -> None:
        """
        Temporarily grant streaming permissions to a user for a given duration.

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
        # Check if user already has streaming permission
        already_allowed = any(Roles.video == role.id for role in user.roles)
        if already_allowed:
            await ctx.send(USER_ALREADY_ALLOWED_TO_STREAM)
            return

        # Schedule task to remove streaming permission from Member
        self.scheduler.schedule_at(duration, user.id, self._remove_streaming_permission(user))
        await user.add_roles(discord.Object(Roles.video), reason="Temporary streaming access granted")
        await ctx.send(f"{Emojis.check_mark}{user.mention} can now stream until "
                       f"{format_infraction_with_duration(str(duration))}.")

    @commands.command(aliases=("unstream", ))
    @commands.has_any_role(*STAFF_ROLES)
    async def revokestream(
            self,
            ctx: commands.Context,
            user: discord.Member
    ) -> None:
        """Take away streaming permission from a user."""
        # Check if user has the streaming permission to begin with
        allowed = any(Roles.video == role.id for role in user.roles)
        if allowed:
            # Cancel scheduled task to take away streaming permission to avoid errors
            if user.id in self.scheduler:
                self.scheduler.cancel(user.id)
            await user.remove_roles(discord.Object(Roles.video))
            await ctx.send(f"{Emojis.check_mark}Streaming permission taken from {user.display_name}")
        else:
            await ctx.send(USER_ALREADY_NOT_ALLOWED_TO_STREAM)


def setup(bot: Bot) -> None:
    """Loads the Stream cog."""
    bot.add_cog(Stream(bot))
