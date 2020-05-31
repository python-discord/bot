import inspect
from pathlib import Path
from typing import Optional, Tuple, Union

from discord import Embed
from discord.ext import commands

from bot.bot import Bot
from bot.constants import URLs

SourceType = Union[commands.HelpCommand, commands.Command, commands.Cog, str]


class SourceConverter(commands.Converter):
    """Convert an argument into a help command, tag, command, or cog."""

    async def convert(self, ctx: commands.Context, argument: str) -> SourceType:
        """Convert argument into source object."""
        if argument.lower().startswith("help"):
            return ctx.bot.help_command

        tags_cog = ctx.bot.get_cog("Tags")

        if argument.lower() in tags_cog._cache:
            tag = argument.lower()
            if tags_cog._cache[tag]["restricted_to"] != "developers":
                return f"/bot/bot/resources/tags/{tags_cog._cache[tag]['restricted_to']}/{tag}.md"
            else:
                return f"/bot/bot/resources/tags/{tag}.md"

        cog = ctx.bot.get_cog(argument)
        if cog:
            return cog

        cmd = ctx.bot.get_command(argument)
        if cmd:
            return cmd

        raise commands.BadArgument(f"Unable to convert `{argument}` to valid command or Cog.")


class BotSource(commands.Cog):
    """Displays information about the bot's source code."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.command(name="source", aliases=("src",))
    async def source_command(self, ctx: commands.Context, *, source_item: SourceConverter = None) -> None:
        """Display information and a GitHub link to the source code of a command, tag, or cog."""
        if not source_item:
            embed = Embed(title="Bot's GitHub Repository")
            embed.add_field(name="Repository", value=f"[Go to GitHub]({URLs.github_bot_repo})")
            embed.set_thumbnail(url="https://avatars1.githubusercontent.com/u/9919")
            await ctx.send(embed=embed)
            return

        url, location, first_line = self.get_source_link(source_item)
        await ctx.send(embed=await self.build_embed(url, source_item, location, first_line))

    def get_source_link(self, source_item: SourceType) -> Tuple[str, str, Optional[int]]:
        """Build GitHub link of source item."""
        if isinstance(source_item, commands.HelpCommand):
            src = type(source_item)
            filename = inspect.getsourcefile(src)
        elif isinstance(source_item, commands.Command):
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
            first_line_no = None
            lines_extension = ""

        file_location = Path(filename).relative_to("/bot/")
        url = f"{URLs.github_bot_repo}/blob/master/{file_location}{lines_extension}"

        return url, file_location, first_line_no or None

    async def build_embed(self, link: str, source_object: SourceType, loc: str, first_line: Optional[int]) -> Embed:
        """Build embed based on source object."""
        if isinstance(source_object, commands.HelpCommand):
            title = "Help Command"
            description = source_object.__doc__.splitlines()[1]
        elif isinstance(source_object, commands.Command):
            if source_object.cog_name == "Alias":
                cmd_name = source_object.callback.__name__.replace("_alias", "")
                cmd = self.bot.get_command(cmd_name.replace("_", " "))
                description = cmd.short_doc
            else:
                description = source_object.short_doc

            title = f"Command: {source_object.qualified_name}"
        elif isinstance(source_object, str):
            title = f"Tag: {source_object.split('/')[-1].split('.')[0]}"
            description = ""
        else:
            title = f"Cog: {source_object.qualified_name}"
            description = source_object.description.splitlines()[0]

        embed = Embed(title=title, description=description)
        embed.add_field(name="Source Code", value=f"[Go to GitHub]({link})")
        line_text = f":{first_line}" if first_line else ""
        embed.set_footer(text=f"{loc}{line_text}")

        return embed


def setup(bot: Bot) -> None:
    """Load the BotSource cog."""
    bot.add_cog(BotSource(bot))
