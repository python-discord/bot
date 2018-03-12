# coding=utf-8

"""
Credit to Rapptz's script used as an example:
https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/formatter.py
Which falls under The MIT License.
"""

import itertools
import logging
from inspect import formatargspec, getfullargspec

from discord.ext.commands import Command, HelpFormatter, Paginator

from bot.constants import HELP_PREFIX

log = logging.getLogger(__name__)


class Formatter(HelpFormatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _add_subcommands_to_page(self, max_width: int, commands: list):
        """
        basically the same function from d.py but changed:
        - to make the helptext appear as a comment
        - to change the indentation to the PEP8 standard: 4 spaces
        """

        for name, command in commands:
            if name in command.aliases:
                # skip aliases
                continue

            entry = "    {0}{1:<{width}} # {2}".format(HELP_PREFIX, name, command.short_doc, width=max_width)
            shortened = self.shorten(entry)
            self._paginator.add_line(shortened)

    async def format(self):
        """
        rewritten help command to make it more python-y

        example of specific command:
        async def <command>(ctx, <args>):
            \"""
            <help text>
            \"""
            await do_<command>(ctx, <args>)

        example of standard help page:
        class <cog1>:
            bot.<command1>() # <command1 help>
        class <cog2>:
            bot.<command2>() # <command2 help>

        # <ending help note>
        """

        self._paginator = Paginator(prefix="```py")

        if isinstance(self.command, Command):
            # strip the command off bot. and ()
            stripped_command = self.command.name.replace(HELP_PREFIX, "").replace("()", "")

            # get the args using the handy inspect module
            argspec = getfullargspec(self.command.callback)
            arguments = formatargspec(*argspec)
            for arg, annotation in argspec.annotations.items():
                # remove module name to only show class name
                # discord.ext.commands.context.Context -> Context
                arguments = arguments.replace(f"{annotation.__module__}.", "")

            # manipulate the argspec to make it valid python when 'calling' the do_<command>
            args_no_type_hints = argspec.args
            for kwarg in argspec.kwonlyargs:
                args_no_type_hints.append("{0}={0}".format(kwarg))
            args_no_type_hints = "({0})".format(", ".join(args_no_type_hints))

            # remove self from the args
            arguments = arguments.replace("self, ", "")
            args_no_type_hints = args_no_type_hints.replace("self, ", "")

            # indent every line in the help message
            helptext = "\n    ".join(self.command.help.split("\n"))

            # prepare the different sections of the help output, and add them to the paginator
            definition = f"async def {stripped_command}{arguments}:"
            doc_elems = [
                '"""',
                helptext,
                '"""'
            ]

            docstring = ""
            for elem in doc_elems:
                docstring += f'    {elem}\n'

            invocation = f"    await do_{stripped_command}{args_no_type_hints}"
            self._paginator.add_line(definition)
            self._paginator.add_line(docstring)
            self._paginator.add_line(invocation)

            return self._paginator.pages

        max_width = self.max_name_size

        def category_check(tup):
            cog = tup[1].cog_name
            # zero width character to make it appear last when put in alphabetical order
            return cog if cog is not None else "\u200bNoCategory"

        command_list = await self.filter_command_list()
        data = sorted(command_list, key=category_check)

        for category, commands in itertools.groupby(data, key=category_check):
            commands = sorted(commands)
            if len(commands) > 0:
                self._paginator.add_line(f"class {category}:")
                self._add_subcommands_to_page(max_width, commands)

        self._paginator.add_line()
        ending_note = self.get_ending_note()
        # make the ending note appear as comments
        ending_note = "# "+ending_note.replace("\n", "\n# ")
        self._paginator.add_line(ending_note)

        return self._paginator.pages
