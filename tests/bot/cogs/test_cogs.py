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
                    # Annoyingly it returns duplicates for each alias so use a set to fix that
                    yield from set(command.walk_commands())

    @staticmethod
    def walk_modules() -> t.Iterator[ModuleType]:
        """Yield imported modules from the bot.cogs subpackage."""
        def on_error(name: str) -> t.NoReturn:
            raise ImportError(name=name)

        for module in pkgutil.walk_packages(cogs.__path__, "bot.cogs.", onerror=on_error):
            if not module.ispkg:
                yield importlib.import_module(module.name)

    @staticmethod
    def walk_cogs(module: ModuleType) -> t.Iterator[commands.Cog]:
        """Yield all cogs defined in an extension."""
        for obj in module.__dict__.values():
            is_cog = isinstance(obj, type) and issubclass(obj, commands.Cog)
            if is_cog and obj.__module__ == module.__name__:
                yield obj

    @staticmethod
    def get_qualified_names(command: commands.Command) -> t.List[str]:
        """Return a list of all qualified names, including aliases, for the `command`."""
        names = [f"{command.full_parent_name} {alias}" for alias in command.aliases]
        names.append(command.qualified_name)

        return names

    def get_all_commands(self) -> t.Iterator[commands.Command]:
        """Yield all commands for all cogs in all extensions."""
        for module in self.walk_modules():
            for cog in self.walk_cogs(module):
                for cmd in self.walk_commands(cog):
                    yield cmd
