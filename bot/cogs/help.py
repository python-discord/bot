import itertools
import logging
from asyncio import TimeoutError
from collections import namedtuple
from contextlib import suppress
from typing import List

from discord import Colour, Embed, NotFound, Member, Message, Reaction, User
from discord.ext.commands import Bot, Cog, Command, Context, Group, HelpCommand
from fuzzywuzzy import fuzz, process

from bot import constants
from bot.constants import Channels, Emojis, STAFF_ROLES
from bot.decorators import redirect_output
from bot.pagination import LinePaginator

log = logging.getLogger(__name__)

COMMANDS_PER_PAGE = 8
DELETE_EMOJI = Emojis.trashcan
PREFIX = constants.Bot.prefix

Category = namedtuple("Category", ["name", "description", "cogs"])


async def help_cleanup(bot: Bot, author: Member, message: Message) -> None:
    """
    Runs the cleanup for the help command.

    Adds the :trashcan: reaction that, when clicked, will delete the help message.
    After a 300 second timeout, the reaction will be removed.
    """
    def check(r: Reaction, u: User) -> bool:
        """Checks the reaction is :trashcan:, the author is original author and messages are the same."""
        return str(r) == DELETE_EMOJI and u.id == author.id and r.message.id == message.id

    await message.add_reaction(DELETE_EMOJI)

    try:
        await bot.wait_for("reaction_add", check=check, timeout=300)
        await message.delete()
    except TimeoutError:
        await message.remove_reaction(DELETE_EMOJI, bot.user)
    except NotFound:
        pass


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
    async def prepare_help_command(self, ctx: Context, command: str = None) -> None:
        """Adjust context to redirect to a new channel if required."""
        self.context = ctx

    async def command_callback(self, ctx: Context, *, command: str = None) -> None:
        """Attempts to match the provided query with a valid command or cog."""
        # the only reason we need to tamper with this is because d.py does not support "categories",
        # so we need to deal with them ourselves.

        # handle any command redirection and adjust context channel accordingly.
        await self.prepare_help_command(ctx, command=command)
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

        # it's either a cog, group, command or subcommand, let super deal with it
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
        for c in await self.filter_commands(self.context.bot.walk_commands()):
            # the the command or group name
            choices.add(str(c))

            if isinstance(c, Command):
                # all aliases if it's just a command
                choices.update(c.aliases)
            else:
                # otherwise we need to add the parent name in
                choices.update(f"{c.full_parent_name} {a}" for a in c.aliases)

        # all cog names
        choices.update(self.context.bot.cogs)

        # all category names
        choices.update(n.category for n in self.context.bot.cogs.values() if hasattr(n, "category"))
        return choices

    async def command_not_found(self, string: str) -> "HelpQueryNotFound":
        """
        Handles when a query does not match a valid command, group, cog or category.

        Will return an instance of the `HelpQueryNotFound` exception with the error message and possible matches.
        """
        choices = await self.get_all_help_choices()
        result = process.extractBests(string, choices, scorer=fuzz.ratio, score_cutoff=80)

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
            matches = "\n".join(f"`{n}`" for n in error.possible_matches)
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
        fmt = f"**```{PREFIX}{name} {command.signature}```**\n"

        # show command aliases
        aliases = ", ".join(f"`{a}`" if not parent else f"`{parent} {a}`" for a in command.aliases)
        if aliases:
            fmt += f"**Can also use:** {aliases}\n\n"

        # check if the user is allowed to run this command
        if not await command.can_run(self.context):
            fmt += "***You cannot run this command.***\n\n"

        fmt += f"*{command.help or 'No details provided.'}*\n"
        embed.description = fmt

        return embed

    async def send_command_help(self, command: Command) -> None:
        """Send help for a single command."""
        embed = await self.command_formatting(command)
        message = await self.context.send(embed=embed)
        await help_cleanup(self.context.bot, self.context.author, message)

    @staticmethod
    def get_commands_brief_details(commands_: List[Command]) -> str:
        """Formats the prefix, command name and signature, and short doc for an iterable of commands."""
        details = ""
        for c in commands_:
            signature = f" {c.signature}" if c.signature else ""
            details += f"\n**`{PREFIX}{c.qualified_name}{signature}`**\n*{c.short_doc or 'No details provided'}*"

        return details

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
        await help_cleanup(self.context.bot, self.context.author, message)

    async def send_cog_help(self, cog: Cog) -> None:
        """Send help for a cog."""
        # sort commands by name, and remove any the user cant run or are hidden.
        commands_ = await self.filter_commands(cog.get_commands(), sort=True)

        embed = Embed()
        embed.set_author(name="Command Help", icon_url=constants.Icons.questionmark)
        embed.description = f"**{cog.qualified_name}**\n*{cog.description}*"

        command_details = self.get_commands_brief_details(commands_)
        if command_details:
            embed.description += f"\n\n**Commands:**\n{command_details}"

        message = await self.context.send(embed=embed)
        await help_cleanup(self.context.bot, self.context.author, message)

    @staticmethod
    def _category_key(cmd: Command) -> str:
        """
        Returns a cog name of a given command for use as a key for `sorted` and `groupby`.

        A zero width space is used as a prefix for results with no cogs to force them last in ordering.
        """
        if cmd.cog:
            with suppress(AttributeError):
                if cmd.cog.category:
                    return f"**{cmd.cog.category}**"
            return f"**{cmd.cog_name}**"
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
        for c in category.cogs:
            all_commands.extend(c.get_commands())

        filtered_commands = await self.filter_commands(all_commands, sort=True)

        lines = [
            f"`{PREFIX}{c.qualified_name}{f' {c.signature}' if c.signature else ''}`"
            f"\n*{c.short_doc or 'No details provided.'}*" for c in filtered_commands
        ]

        description = f"**{category.name}**\n*{category.description}*"

        if lines:
            description += "\n\n**Commands:**"

        await LinePaginator.paginate(
            lines,
            self.context,
            embed,
            prefix=description,
            max_lines=COMMANDS_PER_PAGE,
            max_size=2040
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

            command_details = [
                f"`{PREFIX}{c.qualified_name}{f' {c.signature}' if c.signature else ''}`"
                f"\n*{c.short_doc or 'No details provided.'}*" for c in sorted_commands
            ]

            # Split cogs or categories which have too many commands to fit in one page.
            # The length of commands is included for later use when aggregating into pages for the paginator.
            for i in range(0, len(sorted_commands), COMMANDS_PER_PAGE):
                truncated_fmt = command_details[i:i + COMMANDS_PER_PAGE]
                joined_fmt = "\n".join(truncated_fmt)
                cog_or_category_pages.append((f"**{cog_or_category}**\n{joined_fmt}", len(truncated_fmt)))

        pages = []
        counter = 0
        page = ""
        for fmt, length in cog_or_category_pages:
            counter += length
            if counter > COMMANDS_PER_PAGE:
                # force a new page on paginator even if it falls short of the max pages
                # since we still want to group categories/cogs.
                counter = length
                pages.append(page)
                page = f"{fmt}\n\n"
            else:
                page += f"{fmt}\n\n"

        if page:
            # add any remaining command help that didn't get added in the last iteration above.
            pages.append(page)

        await LinePaginator.paginate(pages, self.context, embed=embed, max_lines=1, max_size=2040)


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
