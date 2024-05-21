import enum
import inspect
from pathlib import Path

from discord import Embed
from discord.ext import commands
from discord.utils import escape_markdown

from bot.bot import Bot
from bot.constants import URLs
from bot.exts.info.tags import TagIdentifier

SourceObject = commands.HelpCommand | commands.Command | commands.Cog | TagIdentifier | commands.ExtensionNotLoaded

class SourceType(enum.StrEnum):
    """The types of source objects recognized by the source command."""

    help_command = enum.auto()
    command = enum.auto()
    cog = enum.auto()
    tag = enum.auto()
    extension_not_loaded = enum.auto()


class BotSource(commands.Cog):
    """Displays information about the bot's source code."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.command(name="source", aliases=("src",))
    async def source_command(
        self,
        ctx: commands.Context,
        *,
        source_item: str | None = None,
    ) -> None:
        """Display information and a GitHub link to the source code of a command, tag, or cog."""
        if not source_item:
            embed = Embed(title="Bot's GitHub Repository")
            embed.add_field(name="Repository", value=f"[Go to GitHub]({URLs.github_bot_repo})")
            embed.set_thumbnail(url="https://avatars1.githubusercontent.com/u/9919")
            await ctx.send(embed=embed)
            return

        obj, source_type = await self.get_source_object(ctx, source_item)
        embed = await self.build_embed(obj, source_type)
        await ctx.send(embed=embed)

    @staticmethod
    async def get_source_object(ctx: commands.Context, argument: str) -> tuple[SourceObject, SourceType]:
        """Convert argument into the source object and source type."""
        if argument.lower() == "help":
            return ctx.bot.help_command, SourceType.help_command

        cog = ctx.bot.get_cog(argument)
        if cog:
            return cog, SourceType.cog

        cmd = ctx.bot.get_command(argument)
        if cmd:
            return cmd, SourceType.command

        tags_cog = ctx.bot.get_cog("Tags")
        show_tag = True

        if not tags_cog:
            show_tag = False
        else:
            identifier = TagIdentifier.from_string(argument.lower())
            if identifier in tags_cog.tags:
                return identifier, SourceType.tag

        escaped_arg = escape_markdown(argument)

        raise commands.BadArgument(
            f"Unable to convert '{escaped_arg}' to valid command{', tag,' if show_tag else ''} or Cog."
        )

    def get_source_link(self, source_item: SourceObject, source_type: SourceType) -> tuple[str, str, int | None]:
        """
        Build GitHub link of source item, return this link, file location and first line number.

        Raise BadArgument if `source_item` is a dynamically-created object (e.g. via internal eval).
        """
        if source_type == SourceType.command:
            source_item = inspect.unwrap(source_item.callback)
            src = source_item.__code__
            filename = src.co_filename
        elif source_type == SourceType.tag:
            tags_cog = self.bot.get_cog("Tags")
            filename = tags_cog.tags[source_item].file_path
        else:
            src = type(source_item)
            try:
                filename = inspect.getsourcefile(src)
            except TypeError:
                raise commands.BadArgument("Cannot get source for a dynamically-created object.")

        if source_type != SourceType.tag:
            try:
                lines, first_line_no = inspect.getsourcelines(src)
            except OSError:
                raise commands.BadArgument("Cannot get source for a dynamically-created object.")

            lines_extension = f"#L{first_line_no}-L{first_line_no+len(lines)-1}"
        else:
            first_line_no = None
            lines_extension = ""

        # Handle tag file location differently than others to avoid errors in some cases
        if not first_line_no:
            file_location = Path(filename)
        else:
            file_location = Path(filename).relative_to(Path.cwd()).as_posix()

        url = f"{URLs.github_bot_repo}/blob/main/{file_location}{lines_extension}"

        return url, file_location, first_line_no or None

    async def build_embed(self, source_object: SourceObject, source_type: SourceType) -> Embed | None:
        """Build embed based on source object."""
        url, location, first_line = self.get_source_link(source_object, source_type)

        if source_type == SourceType.help_command:
            title = "Help Command"
            description = source_object.__doc__.splitlines()[1]
        elif source_type == SourceType.command:
            description = source_object.short_doc
            title = f"Command: {source_object.qualified_name}"
        elif source_type == SourceType.tag:
            title = f"Tag: {source_object}"
            description = ""
        else:
            title = f"Cog: {source_object.qualified_name}"
            description = source_object.description.splitlines()[0]

        embed = Embed(title=title, description=description)
        embed.add_field(name="Source Code", value=f"[Go to GitHub]({url})")
        line_text = f":{first_line}" if first_line else ""
        embed.set_footer(text=f"{location}{line_text}")

        return embed


async def setup(bot: Bot) -> None:
    """Load the BotSource cog."""
    await bot.add_cog(BotSource(bot))
