import datetime
import logging

import discord
from async_rediscache import RedisCache
from discord.ext import commands

from bot.bot import Bot
from bot.constants import Emojis, Guild, Roles, STAFF_ROLES, VideoPermission
from bot.converters import Expiry
from bot.utils.scheduling import Scheduler
from bot.utils.time import format_infraction_with_duration

log = logging.getLogger(__name__)


class Stream(commands.Cog):
    """Grant and revoke streaming permissions from users."""

    # Stores tasks to remove streaming permission
    # User id : timestamp relation
    task_cache = RedisCache()

    def __init__(self, bot: Bot):
        self.bot = bot
        self.scheduler = Scheduler(self.__class__.__name__)
        self.reload_task = self.bot.loop.create_task(self._reload_tasks_from_redis())

    def cog_unload(self) -> None:
        """Cancel all scheduled tasks."""
        self.reload_task.cancel()
        self.reload_task.add_done_callback(lambda _: self.scheduler.cancel_all())

    async def _remove_streaming_permission(self, member: discord.Member) -> None:
        """Remove the streaming permission from the given Member."""
        await self.task_cache.delete(member.id)
        await member.remove_roles(discord.Object(Roles.video), reason="Streaming access revoked")

    async def _reload_tasks_from_redis(self) -> None:
        """Reload outstanding tasks from redis on startup, delete the task if the member has since left the server."""
        await self.bot.wait_until_guild_available()
        items = await self.task_cache.items()
        for key, value in items:
            member = self.bot.get_guild(Guild.id).get_member(key)

            if not member:
                try:
                    member = await self.bot.get_guild(Guild.id).fetch_member(key)
                except discord.errors.NotFound:
                    log.debug(
                        f"Member {key} left the guild before we could schedule "
                        "the revoking of their streaming permissions."
                    )
                    await self.task_cache.delete(key)
                    continue
                except discord.HTTPException as e:
                    log.exception(f"Exception while trying to retrieve member {key} from discord\n{e}")
                    continue
            revoke_time = datetime.datetime.utcfromtimestamp(value)
            log.debug(f"Scheduling {member} ({member.id}) to have streaming permission revoked at {revoke_time}")
            self.scheduler.schedule_at(
                revoke_time,
                key,
                self._remove_streaming_permission(member)
            )

    @commands.command(aliases=("streaming",))
    @commands.has_any_role(*STAFF_ROLES)
    async def stream(self, ctx: commands.Context, user: discord.Member, duration: Expiry = None) -> None:
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
        log.trace(f"Attempting to give temporary streaming permission to {user} ({user.id}).")
        # if duration is none then calculate default duration
        if duration is None:
            now = datetime.datetime.utcnow()
            duration = now + datetime.timedelta(minutes=VideoPermission.default_permission_duration)

        # Check if user already has streaming permission
        already_allowed = any(Roles.video == role.id for role in user.roles)
        if already_allowed:
            await ctx.send(f"{Emojis.cross_mark} This user can already stream.")
            log.debug(f"{user} ({user.id}) already has permission to stream.")
            return

        # Schedule task to remove streaming permission from Member and add it to task cache
        self.scheduler.schedule_at(duration, user.id, self._remove_streaming_permission(user))
        await self.task_cache.set(user.id, duration.timestamp())
        await user.add_roles(discord.Object(Roles.video), reason="Temporary streaming access granted")
        revoke_time = format_infraction_with_duration(str(duration))
        await ctx.send(f"{Emojis.check_mark} {user.mention} can now stream until {revoke_time}.")
        log.debug(f"Successfully given {user} ({user.id}) permission to stream until {revoke_time}.")

    @commands.command(aliases=("pstream",))
    @commands.has_any_role(*STAFF_ROLES)
    async def permanentstream(self, ctx: commands.Context, user: discord.Member) -> None:
        """Permanently grants the given user the permission to stream."""
        log.trace(f"Attempting to give permanent streaming permission to {user} ({user.id}).")
        # Check if user already has streaming permission
        already_allowed = any(Roles.video == role.id for role in user.roles)
        if already_allowed:
            if user.id in self.scheduler:
                self.scheduler.cancel(user.id)
                await self.task_cache.delete(user.id)
                await ctx.send(f"{Emojis.check_mark} Changed temporary permission to permanent.")
                log.debug(f"Successfully upgraded temporary streaming permission for {user} ({user.id}) to permanent.")
                return
            await ctx.send(f"{Emojis.cross_mark} This user can already stream.")
            log.debug(f"{user} ({user.id}) already had permanent streaming permission.")
            return

        await user.add_roles(discord.Object(Roles.video), reason="Permanent streaming access granted")
        await ctx.send(f"{Emojis.check_mark} Permanently granted {user.mention} the permission to stream.")
        log.debug(f"Successfully given {user} ({user.id}) permanent streaming permission.")

    @commands.command(aliases=("unstream", "rstream"))
    @commands.has_any_role(*STAFF_ROLES)
    async def revokestream(self, ctx: commands.Context, user: discord.Member) -> None:
        """Revoke the permission to stream from the given user."""
        log.trace(f"Attempting to remove streaming permission from {user} ({user.id}).")
        # Check if user has the streaming permission to begin with
        allowed = any(Roles.video == role.id for role in user.roles)
        if allowed:
            # Cancel scheduled task to take away streaming permission to avoid errors
            if user.id in self.scheduler:
                self.scheduler.cancel(user.id)
            await self._remove_streaming_permission(user)
            await ctx.send(f"{Emojis.check_mark} Revoked the permission to stream from {user.mention}.")
            log.debug(f"Successfully revoked streaming permission from {user} ({user.id}).")
        else:
            await ctx.send(f"{Emojis.cross_mark} This user already can't stream.")
            log.debug(f"{user} ({user.id}) didn't have the streaming permission to remove!")


def setup(bot: Bot) -> None:
    """Loads the Stream cog."""
    bot.add_cog(Stream(bot))
