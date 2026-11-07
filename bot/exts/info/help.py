import itertools
import re
from collections import namedtuple
from collections.abc import Callable, Iterable
from contextlib import suppress
from typing import Any

from discord import ButtonStyle, Colour, Embed, Emoji, Interaction, PartialEmoji, app_commands, ui
from discord.ext.commands import (
    Bot,
    Cog,
    Command,
    CommandError,
    Context,
    DisabledCommand,
    Group,
    HybridGroup,
)
from rapidfuzz import fuzz, process
from rapidfuzz.utils import default_process

from bot import constants
from bot.constants import Channels, STAFF_AND_COMMUNITY_ROLES
from bot.decorators import redirect_output
from bot.log import get_logger
from bot.pagination import LinePaginator
from bot.utils.hybrid import hybrid_command
from bot.utils.messages import wait_for_deletion

log = get_logger(__name__)

COMMANDS_PER_PAGE = 8
MAX_AUTOCOMPLETE_CHOICES = 25

NOT_ALLOWED_TO_RUN_MESSAGE = "***You cannot run this command.***\n\n"

Category = namedtuple("Category", ["name", "description", "cogs"])


class SubcommandButton(ui.Button):
    """
    A button shown in a group's help embed.

    The button represents a subcommand, and pressing it will edit the help embed to that of the subcommand.
    """

    def __init__(
        self,
        formatter: HelpFormatter,
        command: Command,
        *,
        style: ButtonStyle = ButtonStyle.primary,
        label: str | None = None,
        disabled: bool = False,
        custom_id: str | None = None,
        url: str | None = None,
        emoji: str | Emoji | PartialEmoji | None = None,
        row: int | None = None
    ):
        super().__init__(
            style=style, label=label, disabled=disabled, custom_id=custom_id, url=url, emoji=emoji, row=row
        )

        self.formatter = formatter
        self.command = command

    async def callback(self, interaction: Interaction) -> None:
        """Edits the help embed to that of the subcommand."""
        subcommand = self.command
        if isinstance(subcommand, Group):
            embed, subcommand_view = await self.formatter.format_group_help(subcommand)
        else:
            embed, subcommand_view = await self.formatter.command_formatting(subcommand)

        await interaction.response.edit_message(embed=embed, view=subcommand_view)


class GroupButton(ui.Button):
    """
    A button shown in a subcommand's help embed.

    The button represents the parent command, and pressing it will edit the help embed to that of the parent.
    """

    def __init__(
        self,
        formatter: HelpFormatter,
        command: Command,
        *,
        style: ButtonStyle = ButtonStyle.secondary,
        label: str | None = None,
        disabled: bool = False,
        custom_id: str | None = None,
        url: str | None = None,
        emoji: str | Emoji | PartialEmoji | None = None,
        row: int | None = None
    ):
        super().__init__(
            style=style, label=label, disabled=disabled, custom_id=custom_id, url=url, emoji=emoji, row=row
        )

        self.formatter = formatter
        self.command = command

    async def callback(self, interaction: Interaction) -> None:
        """Edits the help embed to that of the parent."""
        embed, group_view = await self.formatter.format_group_help(self.command.parent)
        await interaction.response.edit_message(embed=embed, view=group_view)


class CommandView(ui.View):
    """
    The view added to any command's help embed.

    If the command has a parent, a button is added to the view to show that parent's help embed.
    """

    def __init__(self, formatter: HelpFormatter, command: Command, context: Context):
        self.context = context
        super().__init__()

        if command.parent:
            self.add_item(GroupButton(formatter, command, emoji="↩️"))

    async def interaction_check(self, interaction: Interaction) -> bool:
        """
        Ensures that the button only works for the user who spawned the help command.

        Also allows moderators to access buttons even when not the author of message.
        """
        if interaction.user is not None:
            if any(role.id in constants.MODERATION_ROLES for role in interaction.user.roles):
                return True

            if interaction.user.id == self.context.author.id:
                return True

        return False


class GroupView(CommandView):
    """
    The view added to a group's help embed.

    The view generates a SubcommandButton for every subcommand the group has.
    """

    MAX_BUTTONS_IN_ROW = 5
    MAX_ROWS = 5

    def __init__(self, formatter: HelpFormatter, group: Group, subcommands: list[Command], context: Context):
        super().__init__(formatter, group, context)
        # Don't add buttons if only a portion of the subcommands can be shown.
        if len(subcommands) + len(self.children) > self.MAX_ROWS * self.MAX_BUTTONS_IN_ROW:
            log.trace(f"Attempted to add navigation buttons for `{group.qualified_name}`, but there was no space.")
            return

        for subcommand in subcommands:
            self.add_item(SubcommandButton(formatter, subcommand, label=subcommand.name))


class HelpQueryNotFoundError(ValueError):
    """
    Raised when a HelpSession Query doesn't match a command or cog.

    Contains the custom attribute of ``possible_matches``.

    Instances of this object contain a dictionary of any command(s) that were close to matching the
    query, where keys are the possible matched command names and values are the likeness match scores.
    """

    def __init__(self, arg: str, possible_matches: dict | None = None):
        super().__init__(arg)
        self.possible_matches = possible_matches


class HelpFormatter:
    """
    Builds and sends the bot's help output.

    Cogs can be grouped into custom categories. All cogs with the same category will be displayed
    under a single category name in the help output. Custom categories are defined inside the cogs
    as a class attribute named `category`. A description can also be specified with the attribute
    `category_description`. If a description is not found in at least one cog, the default will be
    the regular description (class docstring) of the first cog found in the category.
    """

    def __init__(self, context: Context | None = None):
        self.context = context

    def get_bot_mapping(self) -> dict[Cog | None, list[Command]]:
        """Get a mapping of cogs (or None) to the commands they hold."""
        bot = self.context.bot
        mapping = {cog: cog.get_commands() for cog in bot.cogs.values()}
        mapping[None] = [command for command in bot.commands if command.cog is None]
        return mapping

    async def filter_commands(
        self,
        commands_: Iterable[Command],
        *,
        sort: bool = False,
        key: Callable[[Command], Any] | None = None,
    ) -> list[Command]:
        """Remove hidden commands and those the invoker can't run, optionally sorting (by name by default)."""
        if sort and key is None:
            key = lambda c: c.name

        filtered = []
        for command in commands_:
            if command.hidden:
                continue
            try:
                if await command.can_run(self.context):
                    filtered.append(command)
            except CommandError:
                continue

        if sort:
            filtered.sort(key=key)
        return filtered

    def get_usage(self, command: Command) -> str:
        """
        Get the usage line of a command, without any markdown.

        Commands which have an application command are shown as slash commands, anything else
        can only be used by mentioning the bot.
        """
        signature = f" {command.signature}" if command.signature else ""

        if getattr(command, "app_command", None) is not None:
            name = command.qualified_name
            if isinstance(command, HybridGroup) and command.fallback:
                name += f" {command.fallback}"
            return f"/{name}{signature}"

        return f"@{self.context.me.display_name} {command.qualified_name}{signature}"

    def resolve(self, query: str) -> Category | Cog | Command | None:
        """
        Find the category, cog, group, command or subcommand a query refers to.

        Categories are checked first, then cogs, then commands (including aliases and subcommands).
        """
        bot = self.context.bot
        query = query.strip().removeprefix("/")

        cog_matches = []
        description = None
        for cog in bot.cogs.values():
            if getattr(cog, "category", None) == query:
                cog_matches.append(cog)
                if hasattr(cog, "category_description"):
                    description = cog.category_description

        if cog_matches:
            return Category(name=query, description=description, cogs=cog_matches)

        if cog := bot.get_cog(query):
            return cog

        return bot.get_command(query)

    async def send_help_for(self, query: str | None) -> None:
        """Send the help matching the query, or the general help if there is no query."""
        if query is None:
            await self.send_bot_help(self.get_bot_mapping())
            return

        match self.resolve(query):
            case None:
                await self.send_error_message(await self.command_not_found(query))
            case Category() as category:
                await self.send_category_help(category)
            case Cog() as cog:
                await self.send_cog_help(cog)
            case Group() as group:
                await self.send_group_help(group)
            case command:
                await self.send_command_help(command)

    async def get_all_help_choices(self) -> set:
        """
        Get all the possible options for getting help in the bot.

        This will only display commands the author has permission to run.

        These include:
        - Category names
        - Cog names
        - Group command names (and aliases)
        - Command names (and aliases)
        - Subcommand names (with parent group and aliases for subcommand, but not including aliases for group)

        Options and choices are case sensitive.
        """
        # first get all commands including subcommands and full command name aliases
        choices = set()
        for command in await self.filter_commands(self.context.bot.walk_commands()):
            # the the command or group name
            choices.add(str(command))

            if isinstance(command, Command):
                # all aliases if it's just a command
                choices.update(command.aliases)
            else:
                # otherwise we need to add the parent name in
                choices.update(f"{command.full_parent_name} {alias}" for alias in command.aliases)

        # all cog names
        choices.update(self.context.bot.cogs)

        # all category names
        choices.update(cog.category for cog in self.context.bot.cogs.values() if hasattr(cog, "category"))
        return choices

    async def command_not_found(self, query: str) -> HelpQueryNotFoundError:
        """
        Handles when a query does not match a valid command, group, cog or category.

        Will return an instance of the `HelpQueryNotFound` exception with the error message and possible matches.
        """
        choices = list(await self.get_all_help_choices())
        result = process.extract(default_process(query), choices, scorer=fuzz.ratio, score_cutoff=60, processor=None)

        # Trim query to avoid embed limits when sending the error.
        if len(query) >= 100:
            query = query[:100] + "..."

        return HelpQueryNotFoundError(f'Query "{query}" not found.', {choice[0]: choice[1] for choice in result})

    async def send_error_message(self, error: HelpQueryNotFoundError) -> None:
        """Send the error message to the channel."""
        embed = Embed(colour=Colour.red(), title=str(error))

        if getattr(error, "possible_matches", None):
            matches = "\n".join(f"`{match}`" for match in error.possible_matches)
            embed.description = f"**Did you mean:**\n{matches}"

        await self.context.send(embed=embed)

    async def command_formatting(self, command: Command) -> tuple[Embed, CommandView | None]:
        """
        Takes a command and turns it into an embed.

        It will add an author, command signature + help, aliases and a note if the user can't run the command.
        """
        embed = Embed()
        embed.set_author(name="Command Help", icon_url=constants.Icons.questionmark)

        parent = command.full_parent_name

        command_details = f"**```{self.get_usage(command)}```**\n"

        # show command aliases
        aliases = [f"`{alias}`" if not parent else f"`{parent} {alias}`" for alias in command.aliases]
        aliases += [f"`{alias}`" for alias in getattr(command, "root_aliases", ())]
        aliases = ", ".join(sorted(aliases))
        if aliases:
            command_details += f"**Can also use (when mentioning the bot):** {aliases}\n\n"

        # when command is disabled, show message about it,
        # when other CommandError or user is not allowed to run command,
        # add this to help message.
        try:
            if not await command.can_run(self.context):
                command_details += NOT_ALLOWED_TO_RUN_MESSAGE
        except DisabledCommand:
            command_details += "***This command is disabled.***\n\n"
        except CommandError:
            command_details += NOT_ALLOWED_TO_RUN_MESSAGE

        # Remove line breaks from docstrings, if not used to separate paragraphs.
        # Allow overriding this behaviour via putting \u2003 at the start of a line.
        formatted_doc = re.sub("(?<!\n)\n(?![\n\u2003])", " ", command.help) if command.help else None
        command_details += f"{formatted_doc or 'No details provided.'}\n"
        embed.description = command_details

        # If the help is invoked in the context of an error, don't show subcommand navigation.
        view = CommandView(self, command, self.context) if not self.context.command_failed else None
        return embed, view

    async def send_command_help(self, command: Command) -> None:
        """Send help for a single command."""
        embed, view = await self.command_formatting(command)
        message = await self.context.send(embed=embed, view=view)
        await wait_for_deletion(message, (self.context.author.id,))

    def get_commands_brief_details(self, commands_: list[Command], return_as_list: bool = False) -> list[str] | str:
        """
        Formats the usage (command name and signature), and short doc for an iterable of commands.

        return_as_list is helpful for passing these command details into the paginator as a list of command details.
        """
        details = []
        for command in commands_:
            details.append(f"\n**`{self.get_usage(command)}`**\n{command.short_doc or 'No details provided'}")
        if return_as_list:
            return details
        return "".join(details)

    async def format_group_help(self, group: Group) -> tuple[Embed, CommandView | None]:
        """Formats help for a group command."""
        subcommands = group.commands

        if len(subcommands) == 0:
            # no subcommands, just treat it like a regular command
            return await self.command_formatting(group)

        # remove commands that the user can't run and are hidden, and sort by name
        commands_ = await self.filter_commands(subcommands, sort=True)

        embed, _ = await self.command_formatting(group)

        command_details = self.get_commands_brief_details(commands_)
        if command_details:
            embed.description += f"\n**Subcommands:**\n{command_details}"

        # If the help is invoked in the context of an error, don't show subcommand navigation.
        view = GroupView(self, group, commands_, self.context) if not self.context.command_failed else None
        return embed, view

    async def send_group_help(self, group: Group) -> None:
        """Sends help for a group command."""
        embed, view = await self.format_group_help(group)
        message = await self.context.send(embed=embed, view=view)
        await wait_for_deletion(message, (self.context.author.id,))

    async def send_cog_help(self, cog: Cog) -> None:
        """Send help for a cog."""
        # sort commands by name, and remove any the user can't run or are hidden.
        commands_ = await self.filter_commands(cog.get_commands(), sort=True)

        embed = Embed()
        embed.set_author(name="Command Help", icon_url=constants.Icons.questionmark)
        embed.description = f"**{cog.qualified_name}**\n{cog.description}"

        command_details = self.get_commands_brief_details(commands_)
        if command_details:
            embed.description += f"\n\n**Commands:**\n{command_details}"

        message = await self.context.send(embed=embed)
        await wait_for_deletion(message, (self.context.author.id,))

    @staticmethod
    def _category_key(command: Command) -> str:
        """
        Returns a cog name of a given command for use as a key for `sorted` and `groupby`.

        A zero width space is used as a prefix for results with no cogs to force them last in ordering.
        """
        if command.cog:
            with suppress(AttributeError):
                if command.cog.category:
                    return f"**{command.cog.category}**"
            return f"**{command.cog_name}**"
        return "**\u200bNo Category:**"

    async def send_category_help(self, category: Category) -> None:
        """
        Sends help for a bot category.

        This sends a brief help for all commands in all cogs registered to the category.
        """
        embed = Embed()
        embed.set_author(name="Command Help", icon_url=constants.Icons.questionmark)

        all_commands = []
        for cog in category.cogs:
            all_commands.extend(cog.get_commands())

        filtered_commands = await self.filter_commands(all_commands, sort=True)

        command_detail_lines = self.get_commands_brief_details(filtered_commands, return_as_list=True)
        description = f"**{category.name}**\n{category.description}"

        if command_detail_lines:
            description += "\n\n**Commands:**"

        await LinePaginator.paginate(
            command_detail_lines,
            self.context,
            embed,
            prefix=description,
            max_lines=COMMANDS_PER_PAGE,
            max_size=2000,
        )

    async def send_bot_help(self, mapping: dict) -> None:
        """Sends help for all bot commands and cogs."""
        bot = self.context.bot

        embed = Embed()
        embed.set_author(name="Command Help", icon_url=constants.Icons.questionmark)

        filter_commands = await self.filter_commands(bot.commands, sort=True, key=self._category_key)

        cog_or_category_pages = []

        for cog_or_category, _commands in itertools.groupby(filter_commands, key=self._category_key):
            sorted_commands = sorted(_commands, key=lambda c: c.name)

            if len(sorted_commands) == 0:
                continue

            command_detail_lines = self.get_commands_brief_details(sorted_commands, return_as_list=True)

            # Split cogs or categories which have too many commands to fit in one page.
            # The length of commands is included for later use when aggregating into pages for the paginator.
            for index in range(0, len(sorted_commands), COMMANDS_PER_PAGE):
                truncated_lines = command_detail_lines[index:index + COMMANDS_PER_PAGE]
                joined_lines = "".join(truncated_lines)
                cog_or_category_pages.append((f"**{cog_or_category}**{joined_lines}", len(truncated_lines)))

        pages = []
        counter = 0
        page = ""
        for page_details, length in cog_or_category_pages:
            counter += length
            if counter > COMMANDS_PER_PAGE:
                # force a new page on paginator even if it falls short of the max pages
                # since we still want to group categories/cogs.
                counter = length
                pages.append(page)
                page = f"{page_details}\n\n"
            else:
                page += f"{page_details}\n\n"

        if page:
            # add any remaining command help that didn't get added in the last iteration above.
            pages.append(page)

        await LinePaginator.paginate(pages, self.context, embed=embed, max_lines=1, max_size=2000)


def get_autocomplete_choices(choices: Iterable[str], current: str) -> list[str]:
    """
    Select the help choices to suggest for the text typed so far.

    Choices containing the text come first (those starting with it before the others), followed by close fuzzy matches.
    """
    choices = sorted(choices)
    current = current.strip().removeprefix("/").lower()
    if not current:
        return choices[:MAX_AUTOCOMPLETE_CHOICES]

    contained = [choice for choice in choices if current in choice.lower()]
    contained.sort(key=lambda choice: (not choice.lower().startswith(current), len(choice), choice))
    selected = contained[:MAX_AUTOCOMPLETE_CHOICES]

    remaining = MAX_AUTOCOMPLETE_CHOICES - len(selected)
    if remaining:
        others = [choice for choice in choices if choice not in selected]
        fuzzy = process.extract(
            current, others, scorer=fuzz.ratio, score_cutoff=60, limit=remaining, processor=default_process
        )
        selected.extend(choice for choice, *_ in fuzzy)

    return selected


class Help(Cog):
    """Custom Embed Pagination Help feature."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.formatter = HelpFormatter()
        self.old_help_command = bot.help_command
        bot.help_command = None

    async def cog_unload(self) -> None:
        """Reset the help command when the cog is unloaded."""
        self.bot.help_command = self.old_help_command

    @hybrid_command(name="help")
    @app_commands.describe(query="A command, group, cog or category to get help for. Leave empty for all commands")
    @redirect_output(destination_channel=Channels.bot_commands, bypass_roles=STAFF_AND_COMMUNITY_ROLES)
    async def help_command(self, ctx: Context, *, query: str | None = None) -> None:
        """Shows help for bot commands."""
        self.formatter.context = ctx
        await self.formatter.send_help_for(query)

    @help_command.autocomplete("query")
    async def query_autocomplete(self, interaction: Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Suggest the commands, cogs and categories which the invoker can get help for."""
        try:
            ctx = await Context.from_interaction(interaction)
            choices = await HelpFormatter(ctx).get_all_help_choices()
        except Exception:
            log.exception("Failed to build the help autocomplete choices")
            return []

        return [
            app_commands.Choice(name=choice[:100], value=choice[:100])
            for choice in get_autocomplete_choices(choices, current)
        ]


async def setup(bot: Bot) -> None:
    """Load the Help cog."""
    await bot.add_cog(Help(bot))
    log.info("Cog loaded: Help")
