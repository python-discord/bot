
import discord
import sentry_sdk
from discord.ext import commands
from pydis_core.site_api import ResponseCodeError
from pydis_core.utils.channel import get_or_fetch_channel

from bot import constants
from bot.bot import Bot
from bot.log import get_logger
from bot.pagination import LinePaginator

log = get_logger(__name__)
THREAD_BUMP_ENDPOINT = "bot/bumped-threads"


class ThreadBumper(commands.Cog):
    """Cog that allow users to add the current thread to a list that get reopened on archive."""

    def __init__(self, bot: Bot):
        self.bot = bot

    async def thread_exists_in_site(self, thread_id: int) -> bool:
        """Return whether the given thread_id exists in the site api's bump list."""
        # If the thread exists, site returns a 204 with no content.
        # Due to this, `api_client.request()` cannot be used, as it always attempts to decode the response as json.
        # Instead, call the site manually using the api_client's session, to use the auth token logic in the wrapper.

        async with self.bot.api_client.session.get(
            f"{self.bot.api_client._url_for(THREAD_BUMP_ENDPOINT)}/{thread_id}"
        ) as response:
            if response.status == 204:
                return True
            if response.status == 404:
                return False
            # A status other than 204/404 is undefined behaviour from site. Raise error for investigation.
            raise ResponseCodeError(response, response.text())

    async def unarchive_threads_not_manually_archived(self, threads: list[discord.Thread]) -> None:
        """
        Iterate through and unarchive any threads that weren't manually archived recently.

        This is done by extracting the manually archived threads from the audit log.

        Only the last 200 thread_update logs are checked,
        as this is assumed to be more than enough to cover bot downtime.
        """
        guild = self.bot.get_guild(constants.Guild.id)

        recent_manually_archived_thread_ids = []
        async for thread_update in guild.audit_logs(limit=200, action=discord.AuditLogAction.thread_update):
            if getattr(thread_update.after, "archived", False):
                recent_manually_archived_thread_ids.append(thread_update.target.id)

        for thread in threads:
            if thread.id in recent_manually_archived_thread_ids:
                log.info(
                    "#%s (%d) was manually archived. Leaving archived, and removing from bumped threads.",
                    thread.name,
                    thread.id
                )
                await self.bot.api_client.delete(f"{THREAD_BUMP_ENDPOINT}/{thread.id}")
            else:
                await thread.edit(archived=False)

    async def cog_load(self) -> None:
        """Ensure bumped threads are active, since threads could have been archived while the bot was down."""
        await self.bot.wait_until_guild_available()

        threads_to_maybe_bump = []
        with sentry_sdk.start_span(description="Fetch threads to bump from site"):
            bumped_threads_from_site = await self.bot.api_client.get(THREAD_BUMP_ENDPOINT)

        with sentry_sdk.start_span(description="Sync bumped threads in site with current guild state"):
            for thread_id in bumped_threads_from_site:
                try:
                    thread = await get_or_fetch_channel(self.bot, thread_id)
                except discord.NotFound:
                    log.info("Thread %d has been deleted, removing from bumped threads.", thread_id)
                    await self.bot.api_client.delete(f"{THREAD_BUMP_ENDPOINT}/{thread_id}")
                    continue

                if not isinstance(thread, discord.Thread):
                    await self.bot.api_client.delete(f"{THREAD_BUMP_ENDPOINT}/{thread_id}")
                    continue

                if thread.archived:
                    threads_to_maybe_bump.append(thread)

        with sentry_sdk.start_span(description="Unarchive threads that should be bumped"):
            if threads_to_maybe_bump:
                await self.unarchive_threads_not_manually_archived(threads_to_maybe_bump)

    @commands.group(name="bump")
    async def thread_bump_group(self, ctx: commands.Context) -> None:
        """A group of commands to manage the bumping of threads."""
        if not ctx.invoked_subcommand:
            await ctx.send_help(ctx.command)

    @thread_bump_group.command(name="add", aliases=("a",))
    async def add_thread_to_bump_list(self, ctx: commands.Context, thread: discord.Thread | None) -> None:
        """Add a thread to the bump list."""
        if not thread:
            if isinstance(ctx.channel, discord.Thread):
                thread = ctx.channel
            else:
                raise commands.BadArgument("You must provide a thread, or run this command within a thread.")

        if await self.thread_exists_in_site(thread.id):
            raise commands.BadArgument("This thread is already in the bump list.")

        await self.bot.api_client.post(THREAD_BUMP_ENDPOINT, data={"thread_id": thread.id})
        await ctx.send(f":ok_hand:{thread.mention} has been added to the bump list.")

    @thread_bump_group.command(name="remove", aliases=("r", "rem", "d", "del", "delete"))
    async def remove_thread_from_bump_list(self, ctx: commands.Context, thread: discord.Thread | None) -> None:
        """Remove a thread from the bump list."""
        if not thread:
            if isinstance(ctx.channel, discord.Thread):
                thread = ctx.channel
            else:
                raise commands.BadArgument("You must provide a thread, or run this command within a thread.")

        if not await self.thread_exists_in_site(thread.id):
            raise commands.BadArgument("This thread is not in the bump list.")

        await self.bot.api_client.delete(f"{THREAD_BUMP_ENDPOINT}/{thread.id}")
        await ctx.send(f":ok_hand: {thread.mention} has been removed from the bump list.")

    @thread_bump_group.command(name="list", aliases=("get",))
    async def list_all_threads_in_bump_list(self, ctx: commands.Context) -> None:
        """List all the threads in the bump list."""
        lines = [f"<#{thread_id}>" for thread_id in await self.bot.api_client.get(THREAD_BUMP_ENDPOINT)]
        embed = discord.Embed(
            title="Threads in the bump list",
            colour=constants.Colours.blue
        )
        await LinePaginator.paginate(lines, ctx, embed, max_lines=10)

    @commands.Cog.listener()
    async def on_thread_update(self, _: discord.Thread, after: discord.Thread) -> None:
        """
        Listen for thread updates and check if the thread has been archived.

        If the thread has been archived, and is in the bump list, un-archive it.
        """
        if not after.archived:
            return

        if await self.thread_exists_in_site(after.id):
            await self.unarchive_threads_not_manually_archived([after])

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Only allow staff & partner roles to invoke the commands in this cog."""
        return await commands.has_any_role(
            *constants.STAFF_PARTNERS_COMMUNITY_ROLES
        ).predicate(ctx)


async def setup(bot: Bot) -> None:
    """Load the ThreadBumper cog."""
    await bot.add_cog(ThreadBumper(bot))
