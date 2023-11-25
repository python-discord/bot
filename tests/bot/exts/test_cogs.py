"""Test suite for general tests which apply to all cogs."""

import importlib
import pkgutil
import typing as t
import unittest
from collections import defaultdict
from types import ModuleType
from unittest import mock

from discord.ext import commands

from bot import exts


class CommandNameTests(unittest.TestCase):
    """Tests for shadowing command names and aliases."""

    @staticmethod
    def walk_commands(cog: commands.Cog) -> t.Iterator[commands.Command]:
        """An iterator that recursively walks through `cog`'s commands and subcommands."""
        # Can't use Bot.walk_commands() or Cog.get_commands() cause those are instance methods.
        for command in cog.__cog_commands__:
            if command.parent is None:
                yield command
                if isinstance(command, commands.GroupMixin):
                    # Annoyingly it returns duplicates for each alias so use a set to fix that
                    yield from set(command.walk_commands())

    @staticmethod
    def walk_modules() -> t.Iterator[ModuleType]:
        """Yield imported modules from the bot.exts subpackage."""
        def on_error(name: str) -> t.NoReturn:
            raise ImportError(name=name)  # pragma: no cover

        # The mock prevents asyncio.get_event_loop() from being called.
        with mock.patch("discord.ext.tasks.loop"):
            prefix = f"{exts.__name__}."
            for module in pkgutil.walk_packages(exts.__path__, prefix, onerror=on_error):
                if not module.ispkg:
                    yield importlib.import_module(module.name)

    @staticmethod
    def walk_cogs(module: ModuleType) -> t.Iterator[commands.Cog]:
        """Yield all cogs defined in an extension."""
        for obj in module.__dict__.values():
            # Check if it's a class type cause otherwise issubclass() may raise a TypeError.
            is_cog = isinstance(obj, type) and issubclass(obj, commands.Cog)
            if is_cog and obj.__module__ == module.__name__:
                yield obj

    @staticmethod
    def get_qualified_names(command: commands.Command) -> list[str]:
        """Return a list of all qualified names, including aliases, for the `command`."""
        names = [f"{command.full_parent_name} {alias}".strip() for alias in command.aliases]
        names.append(command.qualified_name)
        names += getattr(command, "root_aliases", [])

        return names

    def get_all_commands(self) -> t.Iterator[commands.Command]:
        """Yield all commands for all cogs in all extensions."""
        for module in self.walk_modules():
            for cog in self.walk_cogs(module):
                yield from self.walk_commands(cog)

    def test_names_dont_shadow(self):
        """Names and aliases of commands should be unique."""
        all_names = defaultdict(list)
        for cmd in self.get_all_commands():
            func_name = f"{cmd.module}.{cmd.callback.__qualname__}"

            for name in self.get_qualified_names(cmd):
                with self.subTest(cmd=func_name, name=name):
                    if name in all_names:  # pragma: no cover
                        conflicts = ", ".join(all_names.get(name, ""))
                        self.fail(
                            f"Name '{name}' of the command {func_name} conflicts with {conflicts}."
                        )

                all_names[name].append(func_name)
