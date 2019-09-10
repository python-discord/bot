import inspect
import logging
from typing import Union

from discord import Colour, Embed, Member, User
from discord.ext.commands import (
    Bot, Command, Context, clean_content, command, group
)

from bot.cogs.watchchannels.watchchannel import proxy_user
from bot.converters import TagNameConverter
from bot.pagination import LinePaginator

log = logging.getLogger(__name__)


class Alias:
    """Aliases for commonly used commands."""

    def __init__(self, bot: Bot):
        self.bot = bot

    async def invoke(self, ctx: Context, cmd_name: str, *args, **kwargs) -> None:
        """Invokes a command with args and kwargs."""
        log.debug(f"{cmd_name} was invoked through an alias")
        cmd = self.bot.get_command(cmd_name)
        if not cmd:
            return log.warning(f'Did not find command "{cmd_name}" to invoke.')
        elif not await cmd.can_run(ctx):
            return log.warning(
                f'{str(ctx.author)} tried to run the command "{cmd_name}"'
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

    @command(name="watch", hidden=True)
    async def bigbrother_watch_alias(self, ctx: Context, user: Union[Member, User, proxy_user], *, reason: str) -> None:
        """Alias for invoking <prefix>bigbrother watch [user] [reason]."""
        await self.invoke(ctx, "bigbrother watch", user, reason=reason)

    @command(name="unwatch", hidden=True)
    async def bigbrother_unwatch_alias(self, ctx: Context, user: Union[User, proxy_user], *, reason: str) -> None:
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

    @command(name="rules", hidden=True)
    async def site_rules_alias(self, ctx: Context) -> None:
        """Alias for invoking <prefix>site rules."""
        await self.invoke(ctx, "site rules")

    @command(name="reload", hidden=True)
    async def cogs_reload_alias(self, ctx: Context, *, cog_name: str) -> None:
        """Alias for invoking <prefix>cogs reload [cog_name]."""
        await self.invoke(ctx, "cogs reload", cog_name)

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
        await self.invoke(ctx, "tags get traceback")

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
        """Alias for invoking <prefix>tags get [tag_name]."""
        await self.invoke(ctx, "tags get", tag_name)

    @get_group_alias.command(name="docs", aliases=("doc", "d"), hidden=True)
    async def docs_get_alias(
            self, ctx: Context, symbol: clean_content = None
    ) -> None:
        """Alias for invoking <prefix>docs get [symbol]."""
        await self.invoke(ctx, "docs get", symbol)

    @command(name="nominate", hidden=True)
    async def nomination_add_alias(self, ctx: Context, user: Union[Member, User, proxy_user], *, reason: str) -> None:
        """Alias for invoking <prefix>talentpool add [user] [reason]."""
        await self.invoke(ctx, "talentpool add", user, reason=reason)

    @command(name="unnominate", hidden=True)
    async def nomination_end_alias(self, ctx: Context, user: Union[User, proxy_user], *, reason: str) -> None:
        """Alias for invoking <prefix>nomination end [user] [reason]."""
        await self.invoke(ctx, "nomination end", user, reason=reason)


def setup(bot: Bot) -> None:
    """Alias cog load."""
    bot.add_cog(Alias(bot))
    log.info("Cog loaded: Alias")
