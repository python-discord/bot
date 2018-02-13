# coding=utf-8

"""
Credit to Rapptz's script used as an example:
https://github.com/Rapptz/discord.py/blob/rewrite/discord/ext/commands/formatter.py
Which falls under The MIT License.
"""

import itertools

from discord.ext.commands import HelpFormatter, Paginator

class Formatter(HelpFormatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # basically the same function but changed:
    # - to make the helptext appear as a comment
    # - to change the indentation to the PEP8 standard: 4 spaces
    def _add_subcommands_to_page(self, max_width, commands):
        for name, command in commands:
            if name in command.aliases:
                # skip aliases
                continue

            entry = "    {0:<{width}} # {1}".format(name, command.short_doc, width=max_width)
            shortened = self.shorten(entry)
            self._paginator.add_line(shortened)

    async def format(self):
        self._paginator = Paginator(prefix="```py")

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