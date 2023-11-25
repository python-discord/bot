from datetime import UTC, timedelta
from operator import itemgetter

import arrow
import discord
from arrow import Arrow
from async_rediscache import RedisCache
from discord.ext import commands
from pydis_core.utils import scheduling
from pydis_core.utils.members import get_or_fetch_member

from bot.bot import Bot
from bot.constants import (
    Colours,
    Emojis,
    Guild,
    MODERATION_ROLES,
    Roles,
    STAFF_PARTNERS_COMMUNITY_ROLES,
    VideoPermission,
)
from bot.converters import Expiry
from bot.log import get_logger
from bot.pagination import LinePaginator
from bot.utils import time

log = get_logger(__name__)


class Stream(commands.Cog):
    """Grant and revoke streaming permissions from members."""

    # Stores tasks to remove streaming permission
    # RedisCache[discord.Member.id, UtcPosixTimestamp]
    task_cache = RedisCache()

    def __init__(self, bot: Bot):
        self.bot = bot
        self.scheduler = scheduling.Scheduler(self.__class__.__name__)

    async def _revoke_streaming_permission(self, member: discord.Member) -> None:
        """Remove the streaming permission from the given Member."""
        await self.task_cache.delete(member.id)
        await member.remove_roles(discord.Object(Roles.video), reason="Streaming access revoked")

    async def cog_load(self) -> None:
        """Reload outstanding tasks from redis on startup, delete the task if the member has since left the server."""
        await self.bot.wait_until_guild_available()
        items = await self.task_cache.items()
        guild = self.bot.get_guild(Guild.id)
        for key, value in items:
            member = await get_or_fetch_member(guild, key)

            if not member:
                log.debug(
                    "User with ID %d left the guild before their streaming permissions could be revoked.",
                    key
                )
                await self.task_cache.delete(key)
                continue

            revoke_time = Arrow.utcfromtimestamp(value)
            log.debug(f"Scheduling {member} ({member.id}) to have streaming permission revoked at {revoke_time}")
            self.scheduler.schedule_at(
                revoke_time,
                key,
                self._revoke_streaming_permission(member)
            )

    async def _suspend_stream(self, ctx: commands.Context, member: discord.Member) -> None:
        """Suspend a member's stream."""
        await self.bot.wait_until_guild_available()
        voice_state = member.voice

        if not voice_state:
            return

        # If the user is streaming.
        if voice_state.self_stream:
            # End user's stream by moving them to AFK voice channel and back.
            original_vc = voice_state.channel
            await member.move_to(ctx.guild.afk_channel)
            await member.move_to(original_vc)

            # Notify.
            await ctx.send(f"{member.mention}'s stream has been suspended!")
            log.debug(f"Successfully suspended stream from {member} ({member.id}).")
            return

        log.debug(f"No stream found to suspend from {member} ({member.id}).")

    @commands.command(aliases=("streaming",))
    @commands.has_any_role(*MODERATION_ROLES)
    async def stream(
        self,
        ctx: commands.Context,
        member: discord.Member,
        duration: Expiry = None,
    ) -> None:
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
        """  # noqa: RUF002
        log.trace(f"Attempting to give temporary streaming permission to {member} ({member.id}).")

        if duration is None:
            # Use default duration and convert back to datetime as Embed.timestamp doesn't support Arrow
            duration = arrow.utcnow() + timedelta(minutes=VideoPermission.default_permission_duration)
            duration = duration.datetime
        elif duration.tzinfo is None:
            # Make duration tz-aware.
            # ISODateTime could already include tzinfo, this check is so it isn't overwritten.
            duration.replace(tzinfo=UTC)

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

        await ctx.send(f"{Emojis.check_mark} {member.mention} can now stream until {time.discord_timestamp(duration)}.")

        # Convert here for nicer logging
        humanized_duration = time.humanize_delta(duration, arrow.utcnow(), max_units=2)
        end_time = duration.strftime("%Y-%m-%d %H:%M:%S")
        log.debug(
            f"Successfully gave {member} ({member.id}) permission "
            f"to stream for {humanized_duration} (until {end_time})."
        )

    @commands.command(aliases=("pstream",))
    @commands.has_any_role(*MODERATION_ROLES)
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
    @commands.has_any_role(*MODERATION_ROLES)
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

        else:
            await ctx.send(f"{Emojis.cross_mark} This member doesn't have video permissions to remove!")
            log.debug(f"{member} ({member.id}) didn't have the streaming permission to remove!")

        await self._suspend_stream(ctx, member)

    @commands.command(aliases=("lstream",))
    @commands.has_any_role(*MODERATION_ROLES)
    async def liststream(self, ctx: commands.Context) -> None:
        """Lists all users who aren't staff, partners or members of the python community and have stream permissions."""
        non_staff_partners_community_members_with_stream = [
            member
            for member in ctx.guild.get_role(Roles.video).members
            if not any(role.id in STAFF_PARTNERS_COMMUNITY_ROLES for role in member.roles)
        ]

        # List of tuples (UtcPosixTimestamp, str)
        # So that the list can be sorted on the UtcPosixTimestamp before the message is passed to the paginator.
        streamer_info = []
        for member in non_staff_partners_community_members_with_stream:
            if revoke_time := await self.task_cache.get(member.id):
                # Member only has temporary streaming perms
                revoke_delta = Arrow.utcfromtimestamp(revoke_time).humanize()
                message = f"{member.mention} will have stream permissions revoked {revoke_delta}."
            else:
                message = f"{member.mention} has permanent streaming permissions."

            # If revoke_time is None use max timestamp to force sort to put them at the end
            streamer_info.append(
                (revoke_time or Arrow.max.timestamp(), message)
            )

        if streamer_info:
            # Sort based on duration left of streaming perms
            streamer_info.sort(key=itemgetter(0))

            # Only output the message in the pagination
            lines = [line[1] for line in streamer_info]
            embed = discord.Embed(
                title=f"Members with streaming permission (`{len(lines)}` total)",
                colour=Colours.soft_green
            )
            await LinePaginator.paginate(lines, ctx, embed, max_size=400, empty=False)
        else:
            await ctx.send("No members with stream permissions found.")

    async def cog_unload(self) -> None:
        """Cancel all scheduled tasks."""
        self.scheduler.cancel_all()


async def setup(bot: Bot) -> None:
    """Loads the Stream cog."""
    await bot.add_cog(Stream(bot))
