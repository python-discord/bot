import itertools
import logging
from collections import namedtuple
from contextlib import suppress
from typing import List, Union

from discord import Colour, Embed
from discord.ext.commands import Bot, Cog, Command, CommandError, Context, DisabledCommand, Group, HelpCommand
from fuzzywuzzy import fuzz, process
from fuzzywuzzy.utils import full_process

from bot import constants
from bot.constants import Channels, STAFF_ROLES
from bot.decorators import redirect_output
from bot.pagination import LinePaginator
from bot.utils.messages import wait_for_deletion

log = logging.getLogger(__name__)

COMMANDS_PER_PAGE = 8
PREFIX = constants.Bot.prefix

NOT_ALLOWED_TO_RUN_MESSAGE = "***You cannot run this command.***\n\n"

Category = namedtuple("Category", ["name", "description", "cogs"])


class HelpQueryNotFound(ValueError):
    """
    Raised when a HelpSession Query doesn't match a command or cog.

    Contains the custom attribute of ``possible_matches``.

    Instances of this object contain a dictionary of any command(s) that were close to matching the
    query, where keys are the possible matched command names and values are the likeness match scores.
    """

    def __init__(self, arg: str, possible_matches: dict = None):
        super().__init__(arg)
        self.possible_matches = possible_matches


class CustomHelpCommand(HelpCommand):
    """
    An interactive instance for the bot help command.

    Cogs can be grouped into custom categories. All cogs with the same category will be displayed
    under a single category name in the help output. Custom categories are defined inside the cogs
    as a class attribute named `category`. A description can also be specified with the attribute
    `category_description`. If a description is not found in at least one cog, the default will be
    the regular description (class docstring) of the first cog found in the category.
    """

    def __init__(self):
        super().__init__(command_attrs={"help": "Shows help for bot commands"})

    @redirect_output(destination_channel=Channels.bot_commands, bypass_roles=STAFF_ROLES)
    async def command_callback(self, ctx: Context, *, command: str = None) -> None:
        """Attempts to match the provided query with a valid command or cog."""
        # the only reason we need to tamper with this is because d.py does not support "categories",
        # so we need to deal with them ourselves.

        bot = ctx.bot

        if command is None:
            # quick and easy, send bot help if command is none
            mapping = self.get_bot_mapping()
            await self.send_bot_help(mapping)
            return

        cog_matches = []
        description = None
        for cog in bot.cogs.values():
            if hasattr(cog, "category") and cog.category == command:
                cog_matches.append(cog)
                if hasattr(cog, "category_description"):
                    description = cog.category_description

        if cog_matches:
            category = Category(name=command, description=description, cogs=cog_matches)
            await self.send_category_help(category)
            return

        # it's either a cog, group, command or subcommand; let the parent class deal with it
        await super().command_callback(ctx, command=command)

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

    async def command_not_found(self, string: str) -> "HelpQueryNotFound":
        """
        Handles when a query does not match a valid command, group, cog or category.

        Will return an instance of the `HelpQueryNotFound` exception with the error message and possible matches.
        """
        choices = await self.get_all_help_choices()

        # Run fuzzywuzzy's processor beforehand, and avoid matching if processed string is empty
        # This avoids fuzzywuzzy from raising a warning on inputs with only non-alphanumeric characters
        if (processed := full_process(string)):
            result = process.extractBests(processed, choices, scorer=fuzz.ratio, score_cutoff=60, processor=None)
        else:
            result = []

        return HelpQueryNotFound(f'Query "{string}" not found.', dict(result))

    async def subcommand_not_found(self, command: Command, string: str) -> "HelpQueryNotFound":
        """
        Redirects the error to `command_not_found`.

        `command_not_found` deals with searching and getting best choices for both commands and subcommands.
        """
        return await self.command_not_found(f"{command.qualified_name} {string}")

    async def send_error_message(self, error: HelpQueryNotFound) -> None:
        """Send the error message to the channel."""
        embed = Embed(colour=Colour.red(), title=str(error))

        if getattr(error, "possible_matches", None):
            matches = "\n".join(f"`{match}`" for match in error.possible_matches)
            embed.description = f"**Did you mean:**\n{matches}"

        await self.context.send(embed=embed)

    async def command_formatting(self, command: Command) -> Embed:
        """
        Takes a command and turns it into an embed.

        It will add an author, command signature + help, aliases and a note if the user can't run the command.
        """
        embed = Embed()
        embed.set_author(name="Command Help", icon_url=constants.Icons.questionmark)

        parent = command.full_parent_name

        name = str(command) if not parent else f"{parent} {command.name}"
        command_details = f"**```{PREFIX}{name} {command.signature}```**\n"

        # show command aliases
        aliases = [f"`{alias}`" if not parent else f"`{parent} {alias}`" for alias in command.aliases]
        aliases += [f"`{alias}`" for alias in getattr(command, "root_aliases", ())]
        aliases = ", ".join(sorted(aliases))
        if aliases:
            command_details += f"**Can also use:** {aliases}\n\n"

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

        command_details += f"*{command.help or 'No details provided.'}*\n"
        embed.description = command_details

        return embed

    async def send_command_help(self, command: Command) -> None:
        """Send help for a single command."""
        embed = await self.command_formatting(command)
        message = await self.context.send(embed=embed)
        await wait_for_deletion(message, (self.context.author.id,))

    @staticmethod
    def get_commands_brief_details(commands_: List[Command], return_as_list: bool = False) -> Union[List[str], str]:
        """
        Formats the prefix, command name and signature, and short doc for an iterable of commands.

        return_as_list is helpful for passing these command details into the paginator as a list of command details.
        """
        details = []
        for command in commands_:
            signature = f" {command.signature}" if command.signature else ""
            details.append(
                f"\n**`{PREFIX}{command.qualified_name}{signature}`**\n*{command.short_doc or 'No details provided'}*"
            )
        if return_as_list:
            return details
        else:
            return "".join(details)

    async def send_group_help(self, group: Group) -> None:
        """Sends help for a group command."""
        subcommands = group.commands

        if len(subcommands) == 0:
            # no subcommands, just treat it like a regular command
            await self.send_command_help(group)
            return

        # remove commands that the user can't run and are hidden, and sort by name
        commands_ = await self.filter_commands(subcommands, sort=True)

        embed = await self.command_formatting(group)

        command_details = self.get_commands_brief_details(commands_)
        if command_details:
            embed.description += f"\n**Subcommands:**\n{command_details}"

        message = await self.context.send(embed=embed)
        await wait_for_deletion(message, (self.context.author.id,))

    async def send_cog_help(self, cog: Cog) -> None:
        """Send help for a cog."""
        # sort commands by name, and remove any the user can't run or are hidden.
        commands_ = await self.filter_commands(cog.get_commands(), sort=True)

        embed = Embed()
        embed.set_author(name="Command Help", icon_url=constants.Icons.questionmark)
        embed.description = f"**{cog.qualified_name}**\n*{cog.description}*"

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
        else:
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
        description = f"**{category.name}**\n*{category.description}*"

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


class Help(Cog):
    """Custom Embed Pagination Help feature."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.old_help_command = bot.help_command
        bot.help_command = CustomHelpCommand()
        bot.help_command.cog = self

    def cog_unload(self) -> None:
        """Reset the help command when the cog is unloaded."""
        self.bot.help_command = self.old_help_command


def setup(bot: Bot) -> None:
    """Load the Help cog."""
    bot.add_cog(Help(bot))
    log.info("Cog loaded: Help")
