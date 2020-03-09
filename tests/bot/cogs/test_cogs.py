"""Test suite for general tests which apply to all cogs."""

import typing as t
import unittest

from discord.ext import commands


class CommandNameTests(unittest.TestCase):
    """Tests for shadowing command names and aliases."""

    @staticmethod
    def walk_commands(cog: commands.Cog) -> t.Iterator[commands.Command]:
        """An iterator that recursively walks through `cog`'s commands and subcommands."""
        for command in cog.__cog_commands__:
            if command.parent is None:
                yield command
                if isinstance(command, commands.GroupMixin):
                    yield from command.walk_commands()
