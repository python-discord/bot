import inspect
import os
from typing import Union

from discord.ext.commands import BadArgument, Cog, Command, Context, Converter, HelpCommand

from bot.bot import Bot
from bot.constants import URLs


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

        command = ctx.bot.get_command(argument)
        if command:
            return command

        cog = ctx.bot.get_cog(argument)
        if cog:
            return cog

        raise BadArgument(f"Unable to convert `{argument}` to help command, command or cog.")


class Source(Cog):
    """Cog of Python Discord projects source information."""

    def __init__(self, bot: Bot):
        self.bot = bot

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


def setup(bot: Bot) -> None:
    """Load `Source` cog."""
    bot.add_cog(Source(bot))
