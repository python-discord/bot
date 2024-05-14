"""Contains the Cog that receives discord.py events and defers most actions to other files in the module."""

import contextlib

import discord
from discord.ext import commands, tasks
from pydis_core.utils import scheduling

from bot import constants
from bot.bot import Bot
from bot.exts.help_channels import _caches, _channel
from bot.log import get_logger
from bot.utils.checks import has_any_role_check

log = get_logger(__name__)


class HelpForum(commands.Cog):
    """
    Manage the help channel forum of the guild.

    This system uses Discord's native forum channel feature to handle most of the logic.

    The purpose of this cog is to add additional features, such as stats collection, old post locking
    and helpful automated messages.
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self.scheduler = scheduling.Scheduler(self.__class__.__name__)
        self.help_forum_channel: discord.ForumChannel = None

    async def cog_unload(self) -> None:
        """Cancel all scheduled tasks on unload."""
        self.scheduler.cancel_all()

    async def cog_load(self) -> None:
        """Archive all idle open posts, schedule check for later for active open posts."""
        log.trace("Initialising help forum cog.")
        self.help_forum_channel = self.bot.get_channel(constants.Channels.python_help)
        if not isinstance(self.help_forum_channel, discord.ForumChannel):
            raise TypeError("Channels.python_help is not a forum channel!")
        self.check_all_open_posts_have_close_task.start()

    @tasks.loop(minutes=5)
    async def check_all_open_posts_have_close_task(self) -> None:
        """Check that each open help post has a scheduled task to close, adding one if not."""
        for post in self.help_forum_channel.threads:
            if post.id not in self.scheduler:
                await _channel.maybe_archive_idle_post(post, self.scheduler)

    async def close_check(self, ctx: commands.Context) -> bool:
        """Return True if the channel is a help post, and the user is the claimant or has a whitelisted role."""
        if not _channel.is_help_forum_post(ctx.channel):
            return False

        if ctx.author.id == ctx.channel.owner_id:
            log.trace(f"{ctx.author} is the help channel claimant, passing the check for dormant.")
            self.bot.stats.incr("help.dormant_invoke.claimant")
            return True

        log.trace(f"{ctx.author} is not the help channel claimant, checking roles.")
        has_role = await commands.has_any_role(*constants.HelpChannels.cmd_whitelist).predicate(ctx)
        if has_role:
            self.bot.stats.incr("help.dormant_invoke.staff")
        return has_role

    @commands.group(name="help-forum", aliases=("hf",))
    async def help_forum_group(self,  ctx: commands.Context) -> None:
        """A group of commands that help manage our help forum system."""
        if not ctx.invoked_subcommand:
            await ctx.send_help(ctx.command)

    @help_forum_group.command(name="close", root_aliases=("close", "dormant", "solved"))
    async def close_command(self, ctx: commands.Context) -> None:
        """
        Make the help post this command was called in dormant.

        May only be invoked by the channel's claimant or by mods+.
        """
        # Don't use a discord.py check because the check needs to fail silently.
        if await self.close_check(ctx):
            log.info(f"Close command invoked by {ctx.author} in #{ctx.channel}.")
            await _channel.help_post_closed(ctx.channel)
            if ctx.channel.id in self.scheduler:
                self.scheduler.cancel(ctx.channel.id)

    @help_forum_group.command(name="title", root_aliases=("title",))
    async def rename_help_post(self, ctx: commands.Context, *, title: str) -> None:
        """Rename the help post to the provided title."""
        if not _channel.is_help_forum_post(ctx.channel):
            # Silently fail in channels other than help posts
            return

        if not await has_any_role_check(ctx, constants.Roles.helpers):
            # Silently fail for non-helpers
            return

        await ctx.channel.edit(name=title)

    @commands.Cog.listener("on_message")
    async def new_post_listener(self, message: discord.Message) -> None:
        """Defer application of new post logic for posts in the help forum to the _channel helper."""
        if not isinstance(message.channel, discord.Thread):
            return
        thread = message.channel

        if message.id != thread.id:
            # Opener messages have the same ID as the thread
            return

        if thread.parent_id != self.help_forum_channel.id:
            return

        await _channel.help_post_opened(thread)

        delay = min(constants.HelpChannels.deleted_idle_minutes, constants.HelpChannels.idle_minutes) * 60
        self.scheduler.schedule_later(
            delay,
            thread.id,
            _channel.maybe_archive_idle_post(thread, self.scheduler)
        )

    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread) -> None:
        """Defer application archive logic for posts in the help forum to the _channel helper."""
        if after.parent_id != self.help_forum_channel.id:
            return
        if not before.archived and after.archived:
            await _channel.help_post_archived(after)

    @commands.Cog.listener()
    async def on_raw_thread_delete(self, deleted_thread_event: discord.RawThreadDeleteEvent) -> None:
        """Defer application of deleted post logic for posts in the help forum to the _channel helper."""
        if deleted_thread_event.parent_id == self.help_forum_channel.id:
            await _channel.help_post_deleted(deleted_thread_event)

    @commands.Cog.listener("on_message")
    async def new_post_message_listener(self, message: discord.Message) -> None:
        """Defer application of new message logic for messages in the help forum to the _message helper."""
        if not _channel.is_help_forum_post(message.channel):
            return

        if not message.author.bot and message.author.id != message.channel.owner_id:
            await _caches.posts_with_non_claimant_messages.set(message.channel.id, "sentinel")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Notify a help thread if the owner is no longer a member of the server."""
        for thread in self.help_forum_channel.threads:
            if thread.owner_id != member.id:
                continue

            if thread.archived:
                continue

            log.debug(f"Notifying help thread {thread.id} that owner {member.id} is no longer in the server.")
            with contextlib.suppress(discord.NotFound):
                await thread.send(":warning: The owner of this post is no longer in the server.")
