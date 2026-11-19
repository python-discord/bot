"""Hybrid command classes and decorators which support pydis_core style ``root_aliases``."""

import typing as t

from discord.ext import commands
from discord.utils import MISSING


class _RootAliasesMixin:
    """Stores the ``root_aliases`` keyword argument, mirroring what pydis_core does for non-hybrid commands."""

    root_aliases: t.Sequence[str]

    def _set_root_aliases(self, root_aliases: t.Sequence[str]) -> None:
        if not isinstance(root_aliases, list | tuple):
            raise TypeError("Root aliases of a command must be a list or a tuple of strings.")
        self.root_aliases = root_aliases


class HybridCommand(_RootAliasesMixin, commands.HybridCommand):
    """A hybrid command which supports ``root_aliases``."""

    def __init__(self, *args, root_aliases: t.Sequence[str] = (), **kwargs):
        super().__init__(*args, **kwargs)
        self._set_root_aliases(root_aliases)


class HybridGroup(_RootAliasesMixin, commands.HybridGroup):
    """A hybrid group which supports ``root_aliases``, and creates subcommands of the same type."""

    def __init__(self, *args, root_aliases: t.Sequence[str] = (), **kwargs):
        super().__init__(*args, **kwargs)
        self._set_root_aliases(root_aliases)

    def command(self, *args, **kwargs) -> t.Callable:
        """Decorator which creates a `HybridCommand` subcommand of this group."""
        def decorator(func: t.Callable) -> HybridCommand:
            kwargs.setdefault("parent", self)
            result = hybrid_command(*args, **kwargs)(func)
            self.add_command(result)
            return result

        return decorator

    def group(self, *args, **kwargs) -> t.Callable:
        """Decorator which creates a `HybridGroup` subgroup of this group."""
        def decorator(func: t.Callable) -> HybridGroup:
            kwargs.setdefault("parent", self)
            result = hybrid_group(*args, **kwargs)(func)
            self.add_command(result)
            return result

        return decorator


def hybrid_command(*args, **kwargs) -> t.Callable:
    """Like `discord.ext.commands.hybrid_command`, but creates a `HybridCommand` supporting ``root_aliases``."""
    def decorator(func: t.Callable) -> HybridCommand:
        if isinstance(func, commands.Command):
            raise TypeError("Callback is already a command.")
        name = args[0] if args else kwargs.pop("name", MISSING)
        return HybridCommand(func, name=name, **{k: v for k, v in kwargs.items() if k != "name"})

    return decorator


def hybrid_group(*args, **kwargs) -> t.Callable:
    """Like `discord.ext.commands.hybrid_group`, but creates a `HybridGroup` supporting ``root_aliases``."""
    def decorator(func: t.Callable) -> HybridGroup:
        if isinstance(func, commands.Command):
            raise TypeError("Callback is already a command.")
        name = args[0] if args else kwargs.pop("name", MISSING)
        return HybridGroup(func, name=name, **{k: v for k, v in kwargs.items() if k != "name"})

    return decorator
