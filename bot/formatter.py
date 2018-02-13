# coding=utf-8

"""
Credit to Rapptz's script used as an example:
https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/formatter.py
Which falls under The MIT License.
"""

import itertools
from inspect import formatargspec, getfullargspec

from discord.ext.commands import Command, HelpFormatter, Paginator

from bot.constants import HELP_PREFIX


class Formatter(HelpFormatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _add_subcommands_to_page(self, max_width, commands):
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
            # strip the command of bot. and ()
            stripped_command = self.command.name.replace("()", "")
            # getting args using the handy inspect module
            argspec = getfullargspec(self.command.callback)
            arguments = formatargspec(*argspec)
            args_no_type_hints = ", ".join(argspec[0])
            # remove self from the arguments
            arguments = arguments.replace("self, ", "")
            args_no_type_hints = args_no_type_hints.replace("self, ", "")
            # first line of help containing the command name and arguments
            definition = f"async def {stripped_command}{arguments}:"
            self._paginator.add_line(definition)
            # next few lines containing the help text formatted as a docstring
            self._paginator.add_line(f"    \"\"\"\n    {self.command.help}\n    \"\"\"")
            # last line 'invoking' the command
            self._paginator.add_line(f"    await do_{stripped_command}({args_no_type_hints})")

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
