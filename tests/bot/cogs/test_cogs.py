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
        for name, cls in extension.__dict__.items():
            if isinstance(cls, commands.Cog):
                yield getattr(extension, name)
