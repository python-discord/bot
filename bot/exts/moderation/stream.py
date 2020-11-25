import time

import discord
from async_rediscache import RedisCache
from discord.ext import commands, tasks

from bot.bot import Bot
from bot.constants import Guild, Roles, STAFF_ROLES, TIME_FORMATS

# Constant error messages
NO_USER_SPECIFIED = "Please specify a user"
TIME_FORMAT_NOT_VALID = "Please specify a valid time format ex. 10h or 1day"
TIME_LESS_EQ_0 = "Duration can not be a 0 or lower"
USER_ALREADY_ALLOWED_TO_STREAM = "This user can already stream"
USER_ALREADY_NOT_ALLOWED_TO_STREAM = "This user already can't stream"


# FORMATS holds a combined list of all allowed time units
# made from TIME_FORMATS constant
FORMATS = []
for key, entry in TIME_FORMATS.items():
    FORMATS.extend(entry["aliases"])
    FORMATS.append(key)


class Stream(commands.Cog):
    """Grant and revoke streaming permissions from users."""

    # Data cache storing userid to unix_time relation
    # user id is used to get member who's streaming permission need to be revoked after some time
    # unix_time is a time when user's streaming permission needs tp be revoked in unix time notation
    user_cache = RedisCache()

    def __init__(self, bot: Bot):
        self.bot = bot
        self.remove_permissions.start()
        self.guild_static = None

    @staticmethod
    def _link_from_alias(time_format: str) -> (dict, str):
        """Get TIME_FORMATS key and entry by time format or any of its aliases."""
        for format_key, val in TIME_FORMATS.items():
            if format_key == time_format or time_format in val["aliases"]:
                return TIME_FORMATS[format_key], format_key

    def _parse_time_to_seconds(self, duration: int, time_format: str) -> int:
        """Get time in seconds from duration and time format."""
        return duration * self._link_from_alias(time_format)[0]["mul"]

    @commands.command(aliases=("streaming", "share"))
    @commands.has_any_role(*STAFF_ROLES)
    async def stream(
            self,
            ctx: commands.Context,
            user: discord.Member = None,
            duration: int = 1,
            time_format: str = "h",
            *_
    ) -> None:
        """
        Stream handles <prefix>stream command.

        argument user - required user mention, any errors should be handled by upper level handler
        duration - int must be higher than 0 - defaults to 1
        time_format - str defining what time unit you want to use, must be any of FORMATS - defaults to h
        Command give user permission to stream and takes it away after provided duration
        """
        # Check for required user argument
        # if not provided send NO_USER_SPECIFIED message
        if not user:
            await ctx.send(NO_USER_SPECIFIED)
            return

        # Time can't be negative lol
        if duration <= 0:
            await ctx.send(TIME_LESS_EQ_0)
            return

        # Check if time_format argument is a valid time format
        # eg. d, day etc are aliases for day time format
        if time_format not in FORMATS:
            await ctx.send(TIME_FORMAT_NOT_VALID)
            return

        # Check if user already has streaming permission
        already_allowed = any(Roles.video == role.id for role in user.roles)
        if already_allowed:
            await ctx.send(USER_ALREADY_ALLOWED_TO_STREAM)
            return

        # Set user id - time in redis cache and add streaming permission role
        await self.user_cache.set(user.id, time.time() + self._parse_time_to_seconds(duration, time_format))
        await user.add_roles(discord.Object(Roles.video), reason="Temporary streaming access granted")
        await ctx.send(f"{user.mention} can now stream for {duration} {self._link_from_alias(time_format)[1]}/s")

    @tasks.loop(seconds=30)
    async def remove_permissions(self) -> None:
        """Background loop for removing streaming permission."""
        all_entries = await self.user_cache.items()
        for user_id, delete_time in all_entries:
            if time.time() > delete_time:
                member = self.guild_static.fetch_memebr(user_id)
                if member:
                    await member.remove_roles(discord.Object(Roles.video), reason="Temporary streaming access revoked")
                    await self.user_cache.pop(user_id)

    @remove_permissions.before_loop
    async def await_ready(self) -> None:
        """Wait for bot to be ready before starting remove_permissions loop and get guild by id."""
        await self.bot.wait_until_ready()
        self.guild_static = self.bot.get_guild(Guild.id)

    @commands.command(aliases=("unstream", ))
    @commands.has_any_role(*STAFF_ROLES)
    async def revokestream(
            self,
            ctx: commands.Context,
            user: discord.Member = None
    ) -> None:
        """
        Revokestream handles <prefix>revokestream command.

        argument user - required user mention, any errors should be handled by upper level handler
        command removes streaming permission from a user
        """
        not_allowed = not any(Roles.video == role.id for role in user.roles)
        if not_allowed:
            await user.remove_roles(discord.Object(Roles.video))
        else:
            await ctx.send(USER_ALREADY_NOT_ALLOWED_TO_STREAM)


def setup(bot: Bot) -> None:
    """Loads the Stream cog."""
    bot.add_cog(Stream(bot))
