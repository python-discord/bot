from typing import Union

from discord.ext.commands import BadArgument, Cog, Context, Converter, Command, HelpCommand

from bot.bot import Bot


class SourceConverted(Converter):
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


def setup(bot: Bot) -> None:
    """Load `Source` cog."""
    bot.add_cog(Source(bot))
