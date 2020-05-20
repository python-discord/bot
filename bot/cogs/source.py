import inspect
import os
from typing import Union

from discord import Embed
from discord.ext.commands import BadArgument, Cog, Command, Context, Converter, HelpCommand, command

from bot.bot import Bot
from bot.constants import URLs

CANT_RUN_MESSAGE = "You can't run this command here."
CAN_RUN_MESSAGE = "You are able to run this command."

COG_CHECK_FAIL = "You can't use commands what is in this Cog here."
COG_CHECK_PASS = "You can use commands from this Cog."


class SourceConverter(Converter):
    """Convert argument to help command, command or Cog."""

    async def convert(self, ctx: Context, argument: str) -> Union[HelpCommand, Command, Cog]:
        """
        Convert argument into source object.

        Order how arguments is checked:
        1. When argument is `help`, return bot help command
        2. When argument is valid command, return this command
        3. When argument is valid Cog, return this Cog
        4. Otherwise raise `BadArgument` error
        """
        if argument.lower() == "help":
            return ctx.bot.help_command

        cmd = ctx.bot.get_command(argument)
        if cmd:
            return cmd

        cog = ctx.bot.get_cog(argument)
        if cog:
            return cog

        raise BadArgument(f"Unable to convert `{argument}` to valid command or Cog.")


class Source(Cog):
    """Cog of Python Discord projects source information."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @command(name="source", aliases=("src",))
    async def source_command(self, ctx: Context, *, source_item: SourceConverter = None) -> None:
        """Get GitHub link and information about help command, command or Cog."""
        if not source_item:
            embed = Embed(title="Bot GitHub Repository", url=URLs.github_bot_repo)
            embed.add_field(name="Repository", value=f"[Go to GitHub]({URLs.github_bot_repo})")
            await ctx.send(embed=embed)
            return

        url = self.get_source_link(source_item)
        await ctx.send(embed=await self.build_embed(url, source_item, ctx))

    @staticmethod
    def get_source_link(source_item: Union[HelpCommand, Command, Cog]) -> str:
        """Build GitHub link of source item."""
        if isinstance(source_item, HelpCommand):
            src = type(source_item)
            filename = inspect.getsourcefile(src)
        elif isinstance(source_item, Command):
            src = source_item.callback.__code__
            filename = src.co_filename
        else:
            src = type(source_item)
            filename = inspect.getsourcefile(src)

        lines, first_line_no = inspect.getsourcelines(src)
        file_location = os.path.relpath(filename)

        return f"{URLs.github_bot_repo}/blob/master/{file_location}#L{first_line_no}-L{first_line_no+len(lines)-1}"

    @staticmethod
    async def build_embed(link: str, source_object: Union[HelpCommand, Command, Cog], ctx: Context) -> Embed:
        """Build embed based on source object."""
        if isinstance(source_object, HelpCommand):
            title = "Help"
            description = source_object.__doc__
        elif isinstance(source_object, Command):
            title = source_object.qualified_name
            description = source_object.help
        else:
            title = source_object.qualified_name
            description = source_object.description

        embed = Embed(title=title, description=description, url=link)
        embed.add_field(name="Source Code", value=f"[Go to GitHub]({link})")

        if isinstance(source_object, Command):
            embed.set_footer(text=CAN_RUN_MESSAGE if await source_object.can_run(ctx) else CANT_RUN_MESSAGE)
        elif isinstance(source_object, Cog):
            embed.set_footer(text=COG_CHECK_PASS if source_object.cog_check(ctx) else COG_CHECK_FAIL)

        return embed


def setup(bot: Bot) -> None:
    """Load `Source` cog."""
    bot.add_cog(Source(bot))
