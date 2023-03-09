import inspect
from pathlib import Path
from typing import Optional, Tuple

from discord import Embed, Interaction, app_commands
from discord.ext.commands import BadArgument, Cog, Command, ExtensionNotLoaded, HelpCommand

from bot.bot import Bot
from bot.constants import URLs
from bot.converters import SourceTransformer
from bot.exts.info.tags import TagIdentifier

SourceType = HelpCommand | Command | Cog | TagIdentifier | ExtensionNotLoaded | app_commands.Command | str
HybridCommand = app_commands.Command | Command


class BotSource(Cog):
    """Displays information about the bot's source code."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @app_commands.command(name="source")
    async def source_command(
        self,
        interaction: Interaction,
        *,
        cog_command_or_tag: app_commands.Transform[SourceType, SourceTransformer] = None
    ) -> None:
        """Display information and a GitHub link to the source code of a command, tag, or cog."""
        if not cog_command_or_tag:
            embed = Embed(title="Bot's GitHub Repository")
            embed.add_field(name="Repository", value=f"[Go to GitHub]({URLs.github_bot_repo})")
            embed.set_thumbnail(url="https://avatars1.githubusercontent.com/u/9919")
            await interaction.response.send_message(embed=embed)
            return

        embed = None
        ephemeral = False
        if isinstance(cog_command_or_tag, str):
            description = f"**Unable to convert '{cog_command_or_tag}' to valid command, tag, or cog.**"
            embed = Embed(description=description)
            ephemeral = True

        embed = await self.build_embed(cog_command_or_tag) if not embed else embed
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

    def get_source_link(self, source_object: SourceType) -> Tuple[str, str, Optional[int]]:
        """
        Build GitHub link of source object, return this link, file location and first line number.

        Raise BadArgument if `source_object` is a dynamically-created object (e.g. via internal eval).
        """
        if isinstance(source_object, HybridCommand):
            source_item = inspect.unwrap(source_object.callback)
            src = source_item.__code__
            filename = src.co_filename
        elif issubclass(type(source_object), Cog) or isinstance(source_object, HelpCommand):
            src = type(source_object)
            try:
                filename = inspect.getsourcefile(src)
            except TypeError:
                raise BadArgument("Cannot get source for a dynamically-created object.")
        else:
            tags_cog = self.bot.get_cog("Tags")
            filename = tags_cog.tags[source_object].file_path

        if issubclass(type(source_object), Cog) or isinstance(source_object, HelpCommand | HybridCommand):
            try:
                lines, first_line_no = inspect.getsourcelines(src)
            except OSError:
                raise BadArgument("Cannot get source for a dynamically-created object.")

            lines_extension = f"#L{first_line_no}-L{first_line_no+len(lines)-1}"
        else:
            first_line_no = None
            lines_extension = ""

        # Handle tag file location differently than others to avoid errors in some cases
        if not first_line_no:
            file_location = Path(filename).relative_to('.')
        else:
            file_location = Path(filename).relative_to(Path.cwd()).as_posix()

        url = f"{URLs.github_bot_repo}/blob/main/{file_location}{lines_extension}"

        return url, file_location, first_line_no or None

    async def build_embed(self, source_object: SourceType) -> Optional[Embed]:
        """Build embed based on source object."""
        url, location, first_line = self.get_source_link(source_object)

        if isinstance(source_object, HelpCommand):
            title = "Help Command"
            description = source_object.__doc__.splitlines()[1]
        elif isinstance(source_object, Command):
            description = source_object.short_doc
            title = f"Command: {source_object.qualified_name}"
        elif isinstance(source_object, app_commands.Command):
            description = source_object.description
            title = f"Slash Command: {source_object.qualified_name}"
        elif issubclass(type(source_object), Cog):
            title = f"Cog: {source_object.qualified_name}"
            description = source_object.description.splitlines()[0]
        else:
            title = f"Tag: {source_object}"
            description = ""

        embed = Embed(title=title, description=description)
        embed.add_field(name="Source Code", value=f"[Go to GitHub]({url})")
        line_text = f":{first_line}" if first_line else ""
        embed.set_footer(text=f"{location}{line_text}")

        return embed


async def setup(bot: Bot) -> None:
    """Load the BotSource cog."""
    await bot.add_cog(BotSource(bot))
