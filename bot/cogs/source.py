import inspect
import logging

import discord
from discord.ext import commands

from bot import constants


logger = logging.getLogger(__name__)


class Source(commands.Cog):
    """Send source code url for a specific command."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="source")
    async def command_source(self, ctx: commands.Context, command_name: str = None) -> None:
        """View the source of a command."""
        if command_name is None:
            return await ctx.send("> https://github.com/python-discord/bot")

        command = self.bot.get_command(command_name)
        if command is None:
            return await ctx.send("No such command found.")

        url = self.get_command_url(command)

        prefix = constants.Bot.prefix

        embed = discord.Embed(colour=discord.Colour.red())
        embed.title = "Command Source"
        embed.description = f"**{command.name.capitalize()}**\n"
        embed.description += f"`{prefix}{command.name}`\n\n {url}"

        await ctx.send(embed=embed)

    @staticmethod
    def get_command_url(command: commands.Command) -> str:
        """Make up the url for the source of the command."""
        # Get the source code
        src_code_object = command.callback.__code__

        # Get module name and replace . with /
        module_name = command.callback.__module__
        module_name = module_name.replace(".", "/") + ".py"

        # Get line number and set last line number
        lines_list, starting_line_no = inspect.getsourcelines(src_code_object)
        lines = len(lines_list)
        last_line_no = starting_line_no + lines - 1

        # Make up the url and return
        base_url = "https://github.com/python-discord/bot/tree/master/"
        final_url = f"<{base_url}{module_name}#L{starting_line_no}-L{last_line_no}>"

        return final_url


def setup(bot: commands.Bot) -> None:
    """Load the cog."""
    bot.add_cog(Source(bot))
    logger.info("Source Cog loaded.")
