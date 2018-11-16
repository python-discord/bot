import asyncio
import inspect
import itertools
from collections import namedtuple
from contextlib import suppress

from discord import Colour, Embed, HTTPException
from discord.ext import commands
from fuzzywuzzy import fuzz, process

from bot import constants
from bot.pagination import (
    DELETE_EMOJI, FIRST_EMOJI, LAST_EMOJI,
    LEFT_EMOJI, LinePaginator, RIGHT_EMOJI,
)

REACTIONS = {
    FIRST_EMOJI: 'first',
    LEFT_EMOJI: 'back',
    RIGHT_EMOJI: 'next',
    LAST_EMOJI: 'end',
    DELETE_EMOJI: 'stop'
}

Cog = namedtuple('Cog', ['name', 'description', 'commands'])


class HelpQueryNotFound(ValueError):
    """
    Raised when a HelpSession Query doesn't match a command or cog.

    Contains the custom attribute of ``possible_matches``.

    Attributes
    ----------
    possible_matches: dict
        Any commands that were close to matching the Query.
        The possible matched command names are the keys.
        The likeness match scores are the values.
    """

    def __init__(self, arg, possible_matches=None):
        super().__init__(arg)
        self.possible_matches = possible_matches


class HelpSession:
    """
    An interactive session for bot and command help output.

    Attributes
    ----------
    title: str
        The title of the help message.
    query: Union[:class:`discord.ext.commands.Bot`,
                 :class:`discord.ext.commands.Command]
    description: str
        The description of the query.
    pages: list[str]
        A list of the help content split into manageable pages.
    message: :class:`discord.Message`
        The message object that's showing the help contents.
    destination: :class:`discord.abc.Messageable`
        Where the help message is to be sent to.
    """

    def __init__(self, ctx, *command, cleanup=False, only_can_run=True, show_hidden=False, max_lines=15):
        """
        Creates an instance of the HelpSession class.

        Parameters
        ----------
        ctx: :class:`discord.Context`
            The context of the invoked help command.
        *command: str
            A variable argument of the command being queried.
        cleanup: Optional[bool]
            Set to ``True`` to have the message deleted on timeout.
            If ``False``, it will clear all reactions on timeout.
            Defaults to ``False``.
        only_can_run: Optional[bool]
            Set to ``True`` to hide commands the user can't run.
            Defaults to ``False``.
        show_hidden: Optional[bool]
            Set to ``True`` to include hidden commands.
            Defaults to ``False``.
        max_lines: Optional[int]
            Sets the max number of lines the paginator will add to a
            single page.
            Defaults to 20.
        """

        self._ctx = ctx
        self._bot = ctx.bot
        self.title = "Command Help"

        # set the query details for the session
        if command:
            query_str = ' '.join(command)
            self.query = self._get_query(query_str)
            self.description = self.query.description or self.query.help
        else:
            self.query = ctx.bot
            self.description = self.query.description
        self.author = ctx.author
        self.destination = ctx.author if ctx.bot.pm_help else ctx.channel

        # set the config for the session
        self._cleanup = cleanup
        self._only_can_run = only_can_run
        self._show_hidden = show_hidden
        self._max_lines = max_lines

        # init session states
        self._pages = None
        self._current_page = 0
        self.message = None
        self._timeout_task = None
        self.reset_timeout()

    def _get_query(self, query):
        """
        Attempts to match the provided query with a valid command or cog.

        Parameters
        ----------
        query: str
            The joined string representing the session query.

        Returns
        -------
        Union[:class:`discord.ext.commands.Command`, :class:`Cog`]
        """

        command = self._bot.get_command(query)
        if command:
            return command

        cog = self._bot.cogs.get(query)
        if cog:
            return Cog(
                name=cog.__class__.__name__,
                description=inspect.getdoc(cog),
                commands=[c for c in self._bot.commands if c.instance is cog]
            )

        self._handle_not_found(query)

    def _handle_not_found(self, query):
        """
        Handles when a query does not match a valid command or cog.

        Will pass on possible close matches along with the
        ``HelpQueryNotFound`` exception.

        Parameters
        ----------
        query: str
            The full query that was requested.

        Raises
        ------
        HelpQueryNotFound
        """

        # combine command and cog names
        choices = list(self._bot.all_commands) + list(self._bot.cogs)

        result = process.extractBests(query, choices, scorer=fuzz.ratio, score_cutoff=90)

        raise HelpQueryNotFound(f'Query "{query}" not found.', dict(result))

    async def timeout(self, seconds=30):
        """
        Waits for a set number of seconds, then stops the help session.

        Parameters
        ----------
        seconds: int
            Number of seconds to wait.
        """

        await asyncio.sleep(seconds)
        await self.stop()

    def reset_timeout(self):
        """
        Cancels the original timeout task and sets it again from the start.
        """

        # cancel original if it exists
        if self._timeout_task:
            if not self._timeout_task.cancelled():
                self._timeout_task.cancel()

        # recreate the timeout task
        self._timeout_task = self._bot.loop.create_task(self.timeout())

    async def on_reaction_add(self, reaction, user):
        """
        Event handler for when reactions are added on the help message.

        Parameters
        ----------
        reaction: :class:`discord.Reaction`
            The reaction that was added.
        user: :class:`discord.User`
            The user who added the reaction.
        """

        # ensure it was the relevant session message
        if reaction.message.id != self.message.id:
            return

        # ensure it was the session author who reacted
        if user.id != self.author.id:
            return

        emoji = str(reaction.emoji)

        # check if valid action
        if emoji not in REACTIONS:
            return

        self.reset_timeout()

        # Run relevant action method
        action = getattr(self, f'do_{REACTIONS[emoji]}', None)
        if action:
            await action()

        # remove the added reaction to prep for re-use
        with suppress(HTTPException):
            await self.message.remove_reaction(reaction, user)

    async def on_message_delete(self, message):
        """
        Closes the help session when the help message is deleted.

        Parameters
        ----------
        message: :class:`discord.Message`
            The message that was deleted.
        """

        if message.id == self.message.id:
            await self.stop()

    async def prepare(self):
        """
        Sets up the help session pages, events, message and reactions.
        """

        # create paginated content
        await self.build_pages()

        # setup listeners
        self._bot.add_listener(self.on_reaction_add)
        self._bot.add_listener(self.on_message_delete)

        # Send the help message
        await self.update_page()
        self.add_reactions()

    def add_reactions(self):
        """
        Adds the relevant reactions to the help message based on if
        pagination is required.
        """

        # if paginating
        if len(self._pages) > 1:
            for reaction in REACTIONS:
                self._bot.loop.create_task(self.message.add_reaction(reaction))

        # if single-page
        else:
            self._bot.loop.create_task(self.message.add_reaction(DELETE_EMOJI))

    def _category_key(self, cmd):
        """
        Returns a cog name of a given command. Used as a key for
        ``sorted`` and ``groupby``.

        A zero width space is used as a prefix for results with no cogs
        to force them last in ordering.

        Parameters
        ----------
        cmd: :class:`discord.ext.commands.Command`
            The command object being checked.

        Returns
        -------
        str
        """

        cog = cmd.cog_name
        return f'**{cog}**' if cog else f'**\u200bNo Category:**'

    def _get_command_params(self, cmd):
        """
        Returns the command usage signature.

        This is a custom implementation of ``command.signature`` in
        order to format the command signature without aliases.

        Parameters
        ----------
        cmd: :class:`discord.ext.commands.Command`
            The command object to get the parameters of.

        Returns
        -------
        str
        """

        results = []
        for name, param in cmd.clean_params.items():

            # if argument has a default value
            if param.default is not param.empty:

                if isinstance(param.default, str):
                    show_default = param.default
                else:
                    show_default = param.default is not None

                # if default is not an empty string or None
                if show_default:
                    results.append(f'[{name}={param.default}]')
                else:
                    results.append(f'[{name}]')

            # if variable length argument
            elif param.kind == param.VAR_POSITIONAL:
                results.append(f'[{name}...]')

            # if required
            else:
                results.append(f'<{name}>')

        return f"{cmd.name} {' '.join(results)}"

    async def build_pages(self):
        """
        Builds the list of content pages to be paginated through in the
        help message.

        Returns
        -------
        list[str]
        """

        # Use LinePaginator to restrict embed line height
        paginator = LinePaginator(prefix='', suffix='', max_lines=self._max_lines)

        # show signature if query is a command
        if isinstance(self.query, commands.Command):
            signature = self._get_command_params(self.query)
            paginator.add_line(f'**```{signature}```**')

            if not await self.query.can_run(self._ctx):
                paginator.add_line('***You cannot run this command.***\n')

        # show name if query is a cog
        if isinstance(self.query, Cog):
            paginator.add_line(f'**{self.query.name}**')

        if self.description:
            paginator.add_line(f'*{self.description}*')

        # list all children commands of the queried object
        if isinstance(self.query, (commands.GroupMixin, Cog)):

            # remove hidden commands if session is not wanting hiddens
            if not self._show_hidden:
                filtered = [c for c in self.query.commands if not c.hidden]
            else:
                filtered = self.query.commands

            # if after filter there are no commands, finish up
            if not filtered:
                self._pages = paginator.pages
                return

            # set category to Commands if cog
            if isinstance(self.query, Cog):
                grouped = (('**Commands:**', self.query.commands),)

            # set category to Subcommands if command
            elif isinstance(self.query, commands.Command):
                grouped = (('**Subcommands:**', self.query.commands),)

            # otherwise sort and organise all commands into categories
            else:
                cat_sort = sorted(filtered, key=self._category_key)
                grouped = itertools.groupby(cat_sort, key=self._category_key)

            # process each category
            for category, cmds in grouped:
                cmds = sorted(cmds, key=lambda c: c.name)

                # if there are no commands, skip category
                if len(cmds) == 0:
                    continue

                cat_cmds = []

                # format details for each child command
                for command in cmds:

                    # skip if hidden and hide if session is set to
                    if command.hidden and not self._show_hidden:
                        continue

                    # see if the user can run the command
                    strikeout = ''
                    can_run = await command.can_run(self._ctx)
                    if not can_run:
                        # skip if we don't show commands they can't run
                        if self._only_can_run:
                            continue
                        strikeout = '~~'

                    signature = self._get_command_params(command)
                    prefix = constants.Bot.prefix
                    info = f"{strikeout}**`{prefix}{signature}`**{strikeout}"

                    # handle if the command has no docstring
                    if command.short_doc:
                        cat_cmds.append(f'{info}\n*{command.short_doc}*')
                    else:
                        cat_cmds.append(f'{info}\n*No details provided.*')

                # state var for if the category should be added next
                print_cat = 1
                new_page = True

                for details in cat_cmds:

                    # keep details together, paginating early if it won't fit
                    lines_adding = len(details.split('\n')) + print_cat
                    if paginator._linecount + lines_adding > self._max_lines:
                        paginator._linecount = 0
                        new_page = True
                        paginator.close_page()

                        # new page so print category title again
                        print_cat = 1

                    if print_cat:
                        if new_page:
                            paginator.add_line('')
                        paginator.add_line(category)
                        print_cat = 0

                    paginator.add_line(details)

        # save organised pages to session
        self._pages = paginator.pages

    def embed_page(self, page_number=0):
        """
        Returns an Embed with the requested page formatted within.

        Parameters
        ----------
        page_number: int
            The page to be retrieved. Zero indexed.

        Returns
        -------
        :class:`discord.Embed`
        """

        embed = Embed()

        # if command or cog, add query to title for pages other than first
        if isinstance(self.query, (commands.Command, Cog)) and page_number > 0:
            title = f'Command Help | "{self.query.name}"'
        else:
            title = self.title

        embed.set_author(name=title, icon_url=constants.Icons.questionmark)
        embed.description = self._pages[page_number]

        # add page counter to footer if paginating
        page_count = len(self._pages)
        if page_count > 1:
            embed.set_footer(text=f'Page {self._current_page+1} / {page_count}')

        return embed

    async def update_page(self, page_number=0):
        """
        Sends the intial message, or changes the existing one to the
        given page number.

        Parameters
        ----------
        page_number: int
            The page number to show in the help message.
        """

        self._current_page = page_number
        embed_page = self.embed_page(page_number)

        if not self.message:
            self.message = await self.destination.send(embed=embed_page)
        else:
            await self.message.edit(embed=embed_page)

    @classmethod
    async def start(cls, ctx, *command, **options):
        """
        Create and begin a help session based on the given command
        context.

        Parameters
        ----------
        ctx: :class:`discord.ext.commands.Context`
        The context of the invoked help command.
        *command: str
            A variable argument of the command being queried.
        cleanup: Optional[bool]
            Set to ``True`` to have the message deleted on session end.
            Defaults to ``False``.
        only_can_run: Optional[bool]
            Set to ``True`` to hide commands the user can't run.
            Defaults to ``False``.
        show_hidden: Optional[bool]
            Set to ``True`` to include hidden commands.
            Defaults to ``False``.
        max_lines: Optional[int]
            Sets the max number of lines the paginator will add to a
            single page.
            Defaults to 20.

        Returns
        -------
        :class:`HelpSession`
        """

        session = cls(ctx, *command, **options)
        await session.prepare()

        return session

    async def stop(self):
        """
        Stops the help session, removes event listeners and attempts to
        delete the help message.
        """

        self._bot.remove_listener(self.on_reaction_add)
        self._bot.remove_listener(self.on_message_delete)

        # ignore if permission issue, or the message doesn't exist
        with suppress(HTTPException, AttributeError):
            if self._cleanup:
                await self.message.delete()
            else:
                await self.message.clear_reactions()

    @property
    def is_first_page(self):
        """
        A bool reflecting if session is currently showing the first page.

        Returns
        -------
        bool
        """

        return self._current_page == 0

    @property
    def is_last_page(self):
        """
        A bool reflecting if the session is currently showing the last page.

        Returns
        -------
        bool
        """

        return self._current_page == (len(self._pages)-1)

    async def do_first(self):
        """
        Event that is called when the user requests the first page.
        """

        if not self.is_first_page:
            await self.update_page(0)

    async def do_back(self):
        """
        Event that is called when the user requests the previous page.
        """

        if not self.is_first_page:
            await self.update_page(self._current_page-1)

    async def do_next(self):
        """
        Event that is called when the user requests the next page.
        """

        if not self.is_last_page:
            await self.update_page(self._current_page+1)

    async def do_end(self):
        """
        Event that is called when the user requests the last page.
        """

        if not self.is_last_page:
            await self.update_page(len(self._pages)-1)

    async def do_stop(self):
        """
        Event that is called when the user requests to stop the help session.
        """

        await self.message.delete()


class Help:
    """
    Custom Embed Pagination Help feature
    """
    @commands.command('help')
    async def new_help(self, ctx, *commands):
        """
        Shows Command Help.
        """

        try:
            await HelpSession.start(ctx, *commands)
        except HelpQueryNotFound as error:
            embed = Embed()
            embed.colour = Colour.red()
            embed.title = str(error)

            if error.possible_matches:
                matches = '\n'.join(error.possible_matches.keys())
                embed.description = f'**Did you mean:**\n`{matches}`'

            await ctx.send(embed=embed)


def unload(bot):
    """
    Reinstates the original help command.

    This is run if the cog raises an exception on load, or if the
    extension is unloaded.

    Parameters
    ----------
    bot: :class:`discord.ext.commands.Bot`
        The discord bot client.
    """

    bot.remove_command('help')
    bot.add_command(bot._old_help)


def setup(bot):
    """
    The setup for the help extension.

    This is called automatically on `bot.load_extension` being run.

    Stores the original help command instance on the ``bot._old_help``
    attribute for later reinstatement, before removing it from the
    command registry so the new help command can be loaded successfully.

    If an exception is raised during the loading of the cog, ``unload``
    will be called in order to reinstate the original help command.

    Parameters
    ----------
    bot: `discord.ext.commands.Bot`
        The discord bot client.
    """

    bot._old_help = bot.get_command('help')
    bot.remove_command('help')

    try:
        bot.add_cog(Help())
    except Exception:
        unload(bot)
        raise


def teardown(bot):
    """
    The teardown for the help extension.

    This is called automatically on `bot.unload_extension` being run.

    Calls ``unload`` in order to reinstate the original help command.

    Parameters
    ----------
    bot: `discord.ext.commands.Bot`
        The discord bot client.
    """

    unload(bot)
