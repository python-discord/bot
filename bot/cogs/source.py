import inspect
import logging
import os

import discord
from discord.ext import commands

from bot import constants
from bot.decorators import in_channel

logger = logging.getLogger(__name__)


class Source(commands.Cog):
    """Send source code url for a specific command."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @in_channel(constants.Channels.bot)
    @commands.command(name="source")
    async def command_source(self, ctx: commands.Context, *, command_name: str = None) -> None:
        """View the source of a command."""
        if command_name is None:
            await ctx.send("> https://github.com/python-discord/bot")
            return

        command = self.bot.get_command(command_name)
        if command is None:
            await ctx.send("No such command found.")
            return

        if command.name == "help":
            url = "https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L475-L490"

        else:
            url = self.get_command_url(command)

        prefix = constants.Bot.prefix

        embed = discord.Embed(colour=discord.Colour.red())
        embed.title = "Command Source"
        embed.description = f"**{command.name.capitalize()}**\n"
        embed.description += f"`{prefix}{command.qualified_name}`\n\n {url}"

        await ctx.send(embed=embed)

    @staticmethod
    def get_command_url(command: commands.Command) -> str:
        """Make up the url for the source of the command."""
        # Get the source code
        src = command.callback.__code__
        file_name = src.co_filename

        # get the file path
        file_path = os.path.relpath(file_name).replace('\\', '/')

        # Get line number and set last line number
        lines_list, starting_line_no = inspect.getsourcelines(src)
        lines = len(lines_list)

        # Get module
        module_name = command.callback.__module__
        module_name = module_name.replace(".", "/") + ".py"

        last_line_no = starting_line_no + lines - 1

        # Make up the url and return
        base_url = "https://github.com/python-discord/bot/tree/master/"

        # use the module name if the file path goes into the decorators.
        if "bot/decorators.py" in file_path:
            final_url = f"{base_url}{module_name}#L{starting_line_no}-L{last_line_no}"
        else:
            final_url = f"{base_url}{file_path}#L{starting_line_no}-L{last_line_no}"

        return final_url


def setup(bot: commands.Bot) -> None:
    """Load the cog."""
    bot.add_cog(Source(bot))
    logger.info("Source Cog loaded.")
