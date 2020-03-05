from abc import ABCMeta

from discord.ext.commands import CogMeta


class CogABCMeta(CogMeta, ABCMeta):
    """Metaclass for ABCs meant to be implemented as Cogs."""

    pass
