import typing as t

import discord
from async_rediscache import RedisCache
from discord.ext import commands

from bot import constants
from bot.bot import Bot
from bot.log import get_logger
from bot.pagination import LinePaginator
from bot.utils import scheduling

log = get_logger(__name__)


class ThreadBumper(commands.Cog):
    """Cog that allow users to add the current thread to a list that get reopened on archive."""

    # RedisCache[discord.Thread.id, "sentinel"]
    threads_to_bump = RedisCache()

    def __init__(self, bot: Bot):
        self.bot = bot
        self.init_task = scheduling.create_task(self.ensure_bumped_threads_are_active(), event_loop=self.bot.loop)

    async def ensure_bumped_threads_are_active(self) -> None:
        """Ensure bumped threads are active, since threads could have been archived while the bot was down."""
        await self.bot.wait_until_guild_available()

        for thread_id, _ in await self.threads_to_bump.items():
            if thread := self.bot.get_channel(thread_id):
                if not thread.archived:
                    continue

            try:
                thread = await self.bot.fetch_channel(thread_id)
            except discord.NotFound:
                log.info(f"Thread {thread_id} has been deleted, removing from bumped threads.")
                await self.threads_to_bump.delete(thread_id)
            if thread.archived:
                await thread.edit(archived=False)

    @commands.group(name="bump")
    async def thread_bump_group(self, ctx: commands.Context) -> None:
        """A group of commands to manage the bumping of threads."""
        if not ctx.invoked_subcommand:
            await ctx.send_help(ctx.command)

    @thread_bump_group.command(name="add")
    async def add_thread_to_bump_list(self, ctx: commands.Context, thread: t.Optional[discord.Thread]) -> None:
        """Add a thread to the bump list."""
        await self.init_task

        if not thread:
            if isinstance(ctx.channel, discord.Thread):
                thread = ctx.channel
            else:
                raise commands.BadArgument("You must provide a thread, or run this command within a thread.")

        await self.threads_to_bump.set(thread.id, "sentinel")
        await ctx.send(f":ok_hand:{thread.mention} has been added to the bump list.")

    @thread_bump_group.command(name="remove", aliases=("r", "rem", "d", "del", "delete"))
    async def remove_thread_from_bump_list(self, ctx: commands.Context, thread: t.Optional[discord.Thread]) -> None:
        """Remove a thread from the bump list."""
        await self.init_task

        if not thread:
            if isinstance(ctx.channel, discord.Thread):
                thread = ctx.channel
            else:
                raise commands.BadArgument("You must provide a thread, or run this command within a thread.")

        await self.threads_to_bump.delete(thread.id)
        await ctx.send(f":ok_hand: {thread.mention} has been removed from the bump list.")

    @thread_bump_group.command(name="list", aliases=("get",))
    async def list_all_threads_in_bump_list(self, ctx: commands.Context) -> None:
        """List all the threads in the bump list."""
        await self.init_task

        lines = [f"<#{k}>" for k, _ in await self.threads_to_bump.items()]
        embed = discord.Embed(
            title="Threads in the bump list",
            colour=constants.Colours.blue
        )
        await LinePaginator.paginate(lines, ctx, embed)

    @commands.Cog.listener()
    async def on_thread_update(self, _: discord.Thread, after: discord.Thread) -> None:
        """
        Listen for thread updates and check if the thread has been archived.

        If the thread has been archived, and is in the bump list, un-archive it.
        """
        await self.init_task

        if not after.archived:
            return

        bumped_threads = [k for k, _ in await self.threads_to_bump.items()]
        if after.id in bumped_threads:
            await after.edit(archived=False)

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Only allow staff & partner roles to invoke the commands in this cog."""
        return await commands.has_any_role(
            *constants.STAFF_PARTNERS_COMMUNITY_ROLES
        ).predicate(ctx)


def setup(bot: Bot) -> None:
    """Load the ThreadBumper cog."""
    bot.add_cog(ThreadBumper(bot))
