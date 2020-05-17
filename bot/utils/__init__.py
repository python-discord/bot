from abc import ABCMeta

from discord.ext.commands import CogMeta

from bot.utils.redis_dict import RedisDict

__all__ = ['RedisDict', 'CogABCMeta']


class CogABCMeta(CogMeta, ABCMeta):
    """Metaclass for ABCs meant to be implemented as Cogs."""

    pass
