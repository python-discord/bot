import inspect
import logging

from discord import Colour, Embed
from discord.ext.commands import (
    Cog, Command, Context, Greedy,
    clean_content, command, group,
)

from bot.bot import Bot
from bot.cogs.extensions import Extension
from bot.converters import FetchedMember, TagNameConverter
from bot.pagination import LinePaginator

log = logging.getLogger(__name__)


class Alias (Cog):
    """Aliases for commonly used commands."""

    def __init__(self, bot: Bot):
        self.bot = bot

    async def invoke(self, ctx: Context, cmd_name: str, *args, **kwargs) -> None:
        """Invokes a command with args and kwargs."""
        log.debug(f"{cmd_name} was invoked through an alias")
        cmd = self.bot.get_command(cmd_name)
        if not cmd:
            return log.info(f'Did not find command "{cmd_name}" to invoke.')
        elif not await cmd.can_run(ctx):
            return log.info(
                f'{str(ctx.author)} tried to run the command "{cmd_name}" but lacks permission.'
            )

        await ctx.invoke(cmd, *args, **kwargs)

    @command(name='aliases')
    async def aliases_command(self, ctx: Context) -> None:
        """Show configured aliases on the bot."""
        embed = Embed(
            title='Configured aliases',
            colour=Colour.blue()
        )
        await LinePaginator.paginate(
            (
                f"• `{ctx.prefix}{value.name}` "
                f"=> `{ctx.prefix}{name[:-len('_alias')].replace('_', ' ')}`"
                for name, value in inspect.getmembers(self)
                if isinstance(value, Command) and name.endswith('_alias')
            ),
            ctx, embed, empty=False, max_lines=20
        )

    @command(name="resources", aliases=("resource",), hidden=True)
    async def site_resources_alias(self, ctx: Context) -> None:
        """Alias for invoking <prefix>site resources."""
        await self.invoke(ctx, "site resources")

    @command(name="tools", hidden=True)
    async def site_tools_alias(self, ctx: Context) -> None:
        """Alias for invoking <prefix>site tools."""
        await self.invoke(ctx, "site tools")

    @command(name="watch", hidden=True)
    async def bigbrother_watch_alias(self, ctx: Context, user: FetchedMember, *, reason: str) -> None:
        """Alias for invoking <prefix>bigbrother watch [user] [reason]."""
        await self.invoke(ctx, "bigbrother watch", user, reason=reason)

    @command(name="unwatch", hidden=True)
    async def bigbrother_unwatch_alias(self, ctx: Context, user: FetchedMember, *, reason: str) -> None:
        """Alias for invoking <prefix>bigbrother unwatch [user] [reason]."""
        await self.invoke(ctx, "bigbrother unwatch", user, reason=reason)

    @command(name="home", hidden=True)
    async def site_home_alias(self, ctx: Context) -> None:
        """Alias for invoking <prefix>site home."""
        await self.invoke(ctx, "site home")

    @command(name="faq", hidden=True)
    async def site_faq_alias(self, ctx: Context) -> None:
        """Alias for invoking <prefix>site faq."""
        await self.invoke(ctx, "site faq")

    @command(name="rules", aliases=("rule",), hidden=True)
    async def site_rules_alias(self, ctx: Context, rules: Greedy[int], *_: str) -> None:
        """Alias for invoking <prefix>site rules."""
        await self.invoke(ctx, "site rules", *rules)

    @command(name="reload", hidden=True)
    async def extensions_reload_alias(self, ctx: Context, *extensions: Extension) -> None:
        """Alias for invoking <prefix>extensions reload [extensions...]."""
        await self.invoke(ctx, "extensions reload", *extensions)

    @command(name="defon", hidden=True)
    async def defcon_enable_alias(self, ctx: Context) -> None:
        """Alias for invoking <prefix>defcon enable."""
        await self.invoke(ctx, "defcon enable")

    @command(name="defoff", hidden=True)
    async def defcon_disable_alias(self, ctx: Context) -> None:
        """Alias for invoking <prefix>defcon disable."""
        await self.invoke(ctx, "defcon disable")

    @command(name="exception", hidden=True)
    async def tags_get_traceback_alias(self, ctx: Context) -> None:
        """Alias for invoking <prefix>tags get traceback."""
        await self.invoke(ctx, "tags get", tag_name="traceback")

    @group(name="get",
           aliases=("show", "g"),
           hidden=True,
           invoke_without_command=True)
    async def get_group_alias(self, ctx: Context) -> None:
        """Group for reverse aliases for commands like `tags get`, allowing for `get tags` or `get docs`."""
        pass

    @get_group_alias.command(name="tags", aliases=("tag", "t"), hidden=True)
    async def tags_get_alias(
            self, ctx: Context, *, tag_name: TagNameConverter = None
    ) -> None:
        """
        Alias for invoking <prefix>tags get [tag_name].

        tag_name: str - tag to be viewed.
        """
        await self.invoke(ctx, "tags get", tag_name=tag_name)

    @get_group_alias.command(name="docs", aliases=("doc", "d"), hidden=True)
    async def docs_get_alias(
            self, ctx: Context, symbol: clean_content = None
    ) -> None:
        """Alias for invoking <prefix>docs get [symbol]."""
        await self.invoke(ctx, "docs get", symbol)

    @command(name="nominate", hidden=True)
    async def nomination_add_alias(self, ctx: Context, user: FetchedMember, *, reason: str) -> None:
        """Alias for invoking <prefix>talentpool add [user] [reason]."""
        await self.invoke(ctx, "talentpool add", user, reason=reason)

    @command(name="unnominate", hidden=True)
    async def nomination_end_alias(self, ctx: Context, user: FetchedMember, *, reason: str) -> None:
        """Alias for invoking <prefix>nomination end [user] [reason]."""
        await self.invoke(ctx, "nomination end", user, reason=reason)

    @command(name="nominees", hidden=True)
    async def nominees_alias(self, ctx: Context) -> None:
        """Alias for invoking <prefix>tp watched."""
        await self.invoke(ctx, "talentpool watched")


def setup(bot: Bot) -> None:
    """Load the Alias cog."""
    bot.add_cog(Alias(bot))
