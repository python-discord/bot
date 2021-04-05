import logging
from datetime import timedelta, timezone

import arrow
import discord
from arrow import Arrow
from async_rediscache import RedisCache
from discord.ext import commands

from bot.bot import Bot
from bot.constants import Colours, Emojis, Guild, Roles, STAFF_ROLES, VideoPermission
from bot.converters import Expiry
from bot.utils.scheduling import Scheduler
from bot.utils.time import format_infraction_with_duration

log = logging.getLogger(__name__)


class Stream(commands.Cog):
    """Grant and revoke streaming permissions from members."""

    # Stores tasks to remove streaming permission
    # RedisCache[discord.Member.id, UtcPosixTimestamp]
    task_cache = RedisCache()

    def __init__(self, bot: Bot):
        self.bot = bot
        self.scheduler = Scheduler(self.__class__.__name__)
        self.reload_task = self.bot.loop.create_task(self._reload_tasks_from_redis())

    def cog_unload(self) -> None:
        """Cancel all scheduled tasks."""
        self.reload_task.cancel()
        self.reload_task.add_done_callback(lambda _: self.scheduler.cancel_all())

    async def _revoke_streaming_permission(self, member: discord.Member) -> None:
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
                except discord.HTTPException:
                    log.exception(f"Exception while trying to retrieve member {key} from Discord.")
                    continue
            revoke_time = Arrow.utcfromtimestamp(value)
            log.debug(f"Scheduling {member} ({member.id}) to have streaming permission revoked at {revoke_time}")
            self.scheduler.schedule_at(
                revoke_time,
                key,
                self._revoke_streaming_permission(member)
            )

    @commands.command(aliases=("streaming",))
    @commands.has_any_role(*STAFF_ROLES)
    async def stream(self, ctx: commands.Context, member: discord.Member, duration: Expiry = None) -> None:
        """
        Temporarily grant streaming permissions to a member for a given duration.

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
        log.trace(f"Attempting to give temporary streaming permission to {member} ({member.id}).")

        if duration is None:
            # Use default duration and convert back to datetime as Embed.timestamp doesn't support Arrow
            duration = arrow.utcnow() + timedelta(minutes=VideoPermission.default_permission_duration)
            duration = duration.datetime
        elif duration.tzinfo is None:
            # Make duration tz-aware.
            # ISODateTime could already include tzinfo, this check is so it isn't overwritten.
            duration.replace(tzinfo=timezone.utc)

        # Check if the member already has streaming permission
        already_allowed = any(Roles.video == role.id for role in member.roles)
        if already_allowed:
            await ctx.send(f"{Emojis.cross_mark} {member.mention} can already stream.")
            log.debug(f"{member} ({member.id}) already has permission to stream.")
            return

        # Schedule task to remove streaming permission from Member and add it to task cache
        self.scheduler.schedule_at(duration, member.id, self._revoke_streaming_permission(member))
        await self.task_cache.set(member.id, duration.timestamp())

        await member.add_roles(discord.Object(Roles.video), reason="Temporary streaming access granted")

        # Use embed as embed timestamps do timezone conversions.
        embed = discord.Embed(
            description=f"{Emojis.check_mark} {member.mention} can now stream.",
            colour=Colours.soft_green
        )
        embed.set_footer(text=f"Streaming permission has been given to {member} until")
        embed.timestamp = duration

        # Mention in content as mentions in embeds don't ping
        await ctx.send(content=member.mention, embed=embed)

        # Convert here for nicer logging
        revoke_time = format_infraction_with_duration(str(duration))
        log.debug(f"Successfully gave {member} ({member.id}) permission to stream until {revoke_time}.")

    @commands.command(aliases=("pstream",))
    @commands.has_any_role(*STAFF_ROLES)
    async def permanentstream(self, ctx: commands.Context, member: discord.Member) -> None:
        """Permanently grants the given member the permission to stream."""
        log.trace(f"Attempting to give permanent streaming permission to {member} ({member.id}).")

        # Check if the member already has streaming permission
        if any(Roles.video == role.id for role in member.roles):
            if member.id in self.scheduler:
                # Member has temp permission, so cancel the task to revoke later and delete from cache
                self.scheduler.cancel(member.id)
                await self.task_cache.delete(member.id)

                await ctx.send(f"{Emojis.check_mark} Permanently granted {member.mention} the permission to stream.")
                log.debug(
                    f"Successfully upgraded temporary streaming permission for {member} ({member.id}) to permanent."
                )
                return

            await ctx.send(f"{Emojis.cross_mark} This member can already stream.")
            log.debug(f"{member} ({member.id}) already had permanent streaming permission.")
            return

        await member.add_roles(discord.Object(Roles.video), reason="Permanent streaming access granted")
        await ctx.send(f"{Emojis.check_mark} Permanently granted {member.mention} the permission to stream.")
        log.debug(f"Successfully gave {member} ({member.id}) permanent streaming permission.")

    @commands.command(aliases=("unstream", "rstream"))
    @commands.has_any_role(*STAFF_ROLES)
    async def revokestream(self, ctx: commands.Context, member: discord.Member) -> None:
        """Revoke the permission to stream from the given member."""
        log.trace(f"Attempting to remove streaming permission from {member} ({member.id}).")

        # Check if the member already has streaming permission
        if any(Roles.video == role.id for role in member.roles):
            if member.id in self.scheduler:
                # Member has temp permission, so cancel the task to revoke later and delete from cache
                self.scheduler.cancel(member.id)
                await self.task_cache.delete(member.id)
            await self._revoke_streaming_permission(member)

            await ctx.send(f"{Emojis.check_mark} Revoked the permission to stream from {member.mention}.")
            log.debug(f"Successfully revoked streaming permission from {member} ({member.id}).")
            return

        await ctx.send(f"{Emojis.cross_mark} This member doesn't have video permissions to remove!")
        log.debug(f"{member} ({member.id}) didn't have the streaming permission to remove!")


def setup(bot: Bot) -> None:
    """Loads the Stream cog."""
    bot.add_cog(Stream(bot))
