import itertools
import logging
from asyncio import TimeoutError
from collections import namedtuple
from contextlib import suppress

from discord import Colour, Embed, HTTPException, Member, Message, Reaction, User
from discord.ext.commands import Bot, Cog, Command, Context, Group, HelpCommand
from fuzzywuzzy import fuzz, process

from bot import constants
from bot.constants import Channels, STAFF_ROLES
from bot.decorators import redirect_output
from bot.pagination import DELETE_EMOJI, LinePaginator

log = logging.getLogger(__name__)

COMMANDS_PER_PAGE = 5
PREFIX = constants.Bot.prefix

Category = namedtuple("Category", ["name", "description", "cogs"])


async def help_cleanup(bot: Bot, author: Member, message: Message) -> None:
    """
    Runs the cleanup for the help command.

    Adds a :x: reaction that, when clicked, will delete the help message.
    After a 300 second timeout, the reaction will be removed.
    """
    def check(r: Reaction, u: User) -> bool:
        """Checks the reaction is :x:, the author is original author and messages are the same."""
        return str(r) == DELETE_EMOJI and u.id == author.id and r.message.id == message.id

    await message.add_reaction(DELETE_EMOJI)
    with suppress(HTTPException, TimeoutError):
        _, _ = await bot.wait_for("reaction_add", check=check, timeout=300)
        await message.delete()
        return

    await message.remove_reaction(DELETE_EMOJI, bot.user)


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

    @redirect_output(destination_channel=Channels.bot, bypass_roles=STAFF_ROLES)
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

    def get_all_help_choices(self) -> set:
        """
        Get all the possible options for getting help in the bot.

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
        for c in self.context.bot.walk_commands():
            # the the command or group name
            choices.add(str(c))

            # all aliases if it's just a command
            choices.update(n for n in c.aliases if isinstance(c, Command))

            # else aliases with parent if group. we need to strip() in case it's a Command and `full_parent` is None,
            # otherwise we get 2 commands: ` help` and normal `help`.
            # We could do case-by-case with f-string but this is the cleanest solution
            choices.update(f"{c.full_parent_name} {a}".strip() for a in c.aliases)

            # all cog names
        choices.update(self.context.bot.cogs)

        # all category names
        choices.update(getattr(n, "category", None) for n in self.context.bot.cogs if hasattr(n, "category"))
        return choices

    def command_not_found(self, string: str) -> "HelpQueryNotFound":
        """
        Handles when a query does not match a valid command, group, cog or category.

        Will return an instance of the `HelpQueryNotFound` exception with the error message and possible matches.
        """
        choices = self.get_all_help_choices()
        result = process.extractBests(string, choices, scorer=fuzz.ratio, score_cutoff=90)

        return HelpQueryNotFound(f'Query "{string}" not found.', dict(result))

    def subcommand_not_found(self, command: Command, string: str) -> "HelpQueryNotFound":
        """
        Redirects the error to `command_not_found`.

        `command_not_found` deals with searching and getting best choices for both commands and subcommands.
        """
        return self.command_not_found(f"{command.qualified_name} {string}")

    async def send_error_message(self, error: HelpQueryNotFound) -> None:
        """Send the error message to the channel."""
        embed = Embed(colour=Colour.red(), title=str(error))

        if getattr(error, "possible_matches", None):
            matches = "\n".join(f"`{n}`" for n in error.possible_matches.keys())
            embed.add_field(name="Did you mean:", value=matches)

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
            fmt += "**You cannot run this command.**"

        fmt += f"*{command.help or 'No details provided.'}*\n"
        embed.description = fmt

        return embed

    async def send_command_help(self, command: Command) -> None:
        """Send help for a single command."""
        embed = await self.command_formatting(command)
        message = await self.context.send(embed=embed)
        await help_cleanup(self.context.bot, self.context.author, message)

    async def send_group_help(self, group: Group) -> None:
        """Sends help for a group command."""
        subcommands = group.commands

        if len(subcommands) == 0:
            # no subcommands, just treat it like a regular command
            await self.send_command_help(group)
            return

        # remove commands that the user can't run and are hidden, and sort by name
        _commands = await self.filter_commands(subcommands, sort=True)

        embed = await self.command_formatting(group)

        # add in subcommands with brief help
        # note: the extra f-string around the signature is necessary because otherwise an extra space before the
        # last back tick is present.
        fmt = "\n".join(
            f"**`{PREFIX}{c.qualified_name}{f' {c.signature}' if c.signature else ''}`**"
            f"\n*{c.short_doc or 'No details provided.'}*" for c in _commands
        )
        embed.description += f"\n**Subcommands:**\n{fmt}"
        message = await self.context.send(embed=embed)
        await help_cleanup(self.context.bot, self.context.author, message)

    async def send_cog_help(self, cog: Cog) -> None:
        """Send help for a cog."""
        # sort commands by name, and remove any the user cant run or are hidden.
        _commands = await self.filter_commands(cog.get_commands(), sort=True)

        embed = Embed()
        embed.set_author(name="Command Help", icon_url=constants.Icons.questionmark)
        embed.description = f"**{cog.qualified_name}**\n*{cog.description}*\n\n**Commands:**\n"

        lines = [
            f"`{PREFIX}{c.qualified_name}{f' {c.signature}' if c.signature else ''}`"
            f"\n*{c.short_doc or 'No details provided.'}*\n" for c in _commands
        ]
        embed.description += "\n".join(n for n in lines)

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

        filtered_commands = await self.filter_commands(all_commands, sort=True, key=self._category_key)

        lines = [
            f"`{PREFIX}{c.qualified_name}{f' {c.signature}' if c.signature else ''}`"
            f"\n*{c.short_doc or 'No details provided.'}*" for c in filtered_commands
        ]

        description = f"**{category.name}**\n*{category.description}*\n\n**Commands:**"

        await LinePaginator.paginate(
            lines, self.context, embed, max_lines=COMMANDS_PER_PAGE,
            max_size=2040, description=description, cleanup=True
        )

    async def send_bot_help(self, mapping: dict) -> None:
        """Sends help for all bot commands and cogs."""
        bot = self.context.bot

        embed = Embed()
        embed.set_author(name="Command Help", icon_url=constants.Icons.questionmark)

        filter_commands = await self.filter_commands(bot.commands, sort=True, key=self._category_key)

        lines = []

        for cog_or_category, _commands in itertools.groupby(filter_commands, key=self._category_key):
            sorted_commands = sorted(_commands, key=lambda c: c.name)

            if len(sorted_commands) == 0:
                continue

            fmt = [
                f"`{PREFIX}{c.qualified_name}{f' {c.signature}' if c.signature else ''}`"
                f"\n*{c.short_doc or 'No details provided.'}*" for c in sorted_commands
            ]

            # we can't embed a '\n'.join() inside an f-string so this is a bit of a compromise
            def get_fmt(i: int) -> str:
                """Get a formatted version of commands for an index."""
                return "\n".join(fmt[i:i+COMMANDS_PER_PAGE])

            # this is a bit yuck because moderation category has 8 commands which needs to be split over 2 pages.
            # pretty much it only splits that category, but also gives the number of commands it's adding to
            # the pages every iteration so we can easily use this below rather than trying to split the string.
            lines.extend(
                (
                    (f"**{cog_or_category}**\n{get_fmt(i)}", len(fmt[i:i+COMMANDS_PER_PAGE]))
                    for i in range(0, len(sorted_commands), COMMANDS_PER_PAGE)
                )
            )

        pages = []
        counter = 0
        formatted = ""
        for (fmt, length) in lines:
            counter += length
            if counter > COMMANDS_PER_PAGE:
                # force a new page on paginator even if it falls short of the max pages
                # since we still want to group categories/cogs.
                counter = length
                pages.append(formatted)
                formatted = f"{fmt}\n\n"
                continue
            formatted += f"{fmt}\n\n"

        await LinePaginator.paginate(pages, self.context, embed=embed, max_lines=1, max_size=2040, cleanup=True)


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
