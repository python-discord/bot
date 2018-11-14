import inspect
import logging

from discord import Colour, Embed, TextChannel, User
from discord.ext.commands import (
    Command, Context, clean_content, command, group
)

from bot.converters import TagNameConverter
from bot.pagination import LinePaginator

log = logging.getLogger(__name__)


class Alias:
    """
    Aliases for more used commands
    """

    def __init__(self, bot):
        self.bot = bot

    async def invoke(self, ctx, cmd_name, *args, **kwargs):
        """
        Invokes a command with args and kwargs.
        Fail early through `command.can_run`, and logs warnings.

        :param ctx: Context instance for command call
        :param cmd_name: Name of command/subcommand to be invoked
        :param args: args to be passed to the command
        :param kwargs: kwargs to be passed to the command
        :return: None
        """

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
    async def aliases_command(self, ctx):
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
    async def site_resources_alias(self, ctx):
        """
        Alias for invoking <prefix>site resources.
        """

        await self.invoke(ctx, "site resources")

    @command(name="watch", hidden=True)
    async def bigbrother_watch_alias(
            self, ctx, user: User, channel: TextChannel = None
    ):
        """
        Alias for invoking <prefix>bigbrother watch user [text_channel].
        """

        await self.invoke(ctx, "bigbrother watch", user, channel)

    @command(name="unwatch", hidden=True)
    async def bigbrother_unwatch_alias(self, ctx, user: User):
        """
        Alias for invoking <prefix>bigbrother unwatch user.

        user: discord.User - A user instance to unwatch
        """

        await self.invoke(ctx, "bigbrother unwatch", user)

    @command(name="home", hidden=True)
    async def site_home_alias(self, ctx):
        """
        Alias for invoking <prefix>site home.
        """

        await self.invoke(ctx, "site home")

    @command(name="faq", hidden=True)
    async def site_faq_alias(self, ctx):
        """
        Alias for invoking <prefix>site faq.
        """

        await self.invoke(ctx, "site faq")

    @command(name="rules", hidden=True)
    async def site_rules_alias(self, ctx):
        """
        Alias for invoking <prefix>site rules.
        """

        await self.invoke(ctx, "site rules")

    @command(name="reload", hidden=True)
    async def cogs_reload_alias(self, ctx, *, cog_name: str):
        """
        Alias for invoking <prefix>cogs reload cog_name.

        cog_name: str - name of the cog to be reloaded.
        """

        await self.invoke(ctx, "cogs reload", cog_name)

    @command(name="defon", hidden=True)
    async def defcon_enable_alias(self, ctx):
        """
        Alias for invoking <prefix>defcon enable.
        """

        await self.invoke(ctx, "defcon enable")

    @command(name="defoff", hidden=True)
    async def defcon_disable_alias(self, ctx):
        """
        Alias for invoking <prefix>defcon disable.
        """

        await self.invoke(ctx, "defcon disable")

    @group(name="get",
           aliases=("show", "g"),
           hidden=True,
           invoke_without_command=True)
    async def get_group_alias(self, ctx):
        """
        Group for reverse aliases for commands like `tags get`,
        allowing for `get tags` or `get docs`.
        """

        pass

    @get_group_alias.command(name="tags", aliases=("tag", "t"), hidden=True)
    async def tags_get_alias(
            self, ctx: Context, *, tag_name: TagNameConverter=None
    ):
        """
        Alias for invoking <prefix>tags get [tag_name].

        tag_name: str - tag to be viewed.
        """

        await self.invoke(ctx, "tags get", tag_name)

    @get_group_alias.command(name="docs", aliases=("doc", "d"), hidden=True)
    async def docs_get_alias(
            self, ctx: Context, symbol: clean_content = None
    ):
        """
        Alias for invoking <prefix>docs get [symbol].

        symbol: str - name of doc to be viewed.
        """

        await self.invoke(ctx, "docs get", symbol)


def setup(bot):
    bot.add_cog(Alias(bot))
    log.info("Cog loaded: Alias")
