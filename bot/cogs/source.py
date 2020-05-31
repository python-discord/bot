import inspect
import os
from typing import Union

from discord import Embed
from discord.ext.commands import BadArgument, Cog, Command, Context, Converter, HelpCommand, command

from bot.bot import Bot
from bot.constants import URLs


class SourceConverter(Converter):
    """Convert an argument into a help command, tag, command, or cog."""

    async def convert(self, ctx: Context, argument: str) -> Union[HelpCommand, Command, Cog, str]:
        """Convert argument into source object."""
        if argument.lower() == "help":
            return ctx.bot.help_command

        tags_cog = ctx.bot.get_cog("Tags")

        if argument.lower() in tags_cog._cache:
            tag = argument.lower()
            if tags_cog._cache[tag]["restricted_to"] != "developers":
                return f"bot/resources/tags/{tags_cog._cache[tag]['restricted_to']}/{tag}.md"
            else:
                return f"bot/resources/tags/{tag}.md"

        cmd = ctx.bot.get_command(argument)
        if cmd:
            return cmd

        cog = ctx.bot.get_cog(argument)
        if cog:
            return cog

        raise BadArgument(f"Unable to convert `{argument}` to valid command or Cog.")


class BotSource(Cog):
    """Displays information about the bot's source code."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @command(name="source", aliases=("src",))
    async def source_command(self, ctx: Context, *, source_item: SourceConverter = None) -> None:
        """Display information and a GitHub link to the source code of a command, tag, or cog."""
        if not source_item:
            embed = Embed(title="Bot GitHub Repository")
            embed.add_field(name="Repository", value=f"[Go to GitHub]({URLs.github_bot_repo})")
            await ctx.send(embed=embed)
            return

        url = self.get_source_link(source_item)
        await ctx.send(embed=await self.build_embed(url, source_item))

    def get_source_link(self, source_item: Union[HelpCommand, Command, Cog, str]) -> str:
        """Build GitHub link of source item."""
        if isinstance(source_item, HelpCommand):
            src = type(source_item)
            filename = inspect.getsourcefile(src)
        elif isinstance(source_item, Command):
            if source_item.cog_name == "Alias":
                cmd_name = source_item.callback.__name__.replace("_alias", "")
                cmd = self.bot.get_command(cmd_name.replace("_", " "))
                src = cmd.callback.__code__
                filename = src.co_filename
            else:
                src = source_item.callback.__code__
                filename = src.co_filename
        elif isinstance(source_item, str):
            filename = source_item
        else:
            src = type(source_item)
            filename = inspect.getsourcefile(src)

        if not isinstance(source_item, str):
            lines, first_line_no = inspect.getsourcelines(src)
            lines_extension = f"#L{first_line_no}-L{first_line_no+len(lines)-1}"
        else:
            lines_extension = ""

        file_location = os.path.relpath(filename)

        return f"{URLs.github_bot_repo}/blob/master/{file_location}{lines_extension}"

    async def build_embed(self, link: str, source_object: Union[HelpCommand, Command, Cog]) -> Embed:
        """Build embed based on source object."""
        if isinstance(source_object, HelpCommand):
            title = "Help"
            description = source_object.__doc__
        elif isinstance(source_object, Command):
            if source_object.cog_name == "Alias":
                cmd_name = source_object.callback.__name__.replace("_alias", "")
                cmd = self.bot.get_command(cmd_name.replace("_", " "))
                description = cmd.help
            else:
                description = source_object.help

            title = source_object.qualified_name
        elif isinstance(source_object, str):
            title = f"Tag: {source_object.split('/')[-1].split('.')[0]}"
            description = ""
        else:
            title = source_object.qualified_name
            description = source_object.description

        embed = Embed(title=title, description=description)
        embed.add_field(name="Source Code", value=f"[Go to GitHub]({link})")

        return embed


def setup(bot: Bot) -> None:
    """Load the BotSource cog."""
    bot.add_cog(BotSource(bot))
