"""Test suite for general tests which apply to all cogs."""

import importlib
import pkgutil
import typing as t
import unittest
from types import ModuleType

from discord.ext import commands

from bot import cogs


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

    @staticmethod
    def walk_extensions() -> t.Iterator[ModuleType]:
        """Yield imported extensions (modules) from the bot.cogs subpackage."""
        for module in pkgutil.iter_modules(cogs.__path__, "bot.cogs."):
            yield importlib.import_module(module.name)

    @staticmethod
    def walk_cogs(extension: ModuleType) -> t.Iterator[commands.Cog]:
        """Yield all cogs defined in an extension."""
        for obj in extension.__dict__.values():
            is_cog = isinstance(obj, type) and issubclass(obj, commands.Cog)
            if is_cog and obj.__module__ == extension.__name__:
                yield obj

    @staticmethod
    def get_qualified_names(command: commands.Command) -> t.List[str]:
        """Return a list of all qualified names, including aliases, for the `command`."""
        names = [f"{command.full_parent_name} {alias}" for alias in command.aliases]
        names.append(command.qualified_name)

        return names

    def get_all_commands(self) -> t.Iterator[commands.Command]:
        """Yield all commands for all cogs in all extensions."""
        for extension in self.walk_extensions():
            for cog in self.walk_cogs(extension):
                for cmd in self.walk_commands(cog):
                    yield cmd
