from abc import ABCMeta

from discord.ext.commands import CogMeta

from bot.utils.redis_cache import RedisCache

__all__ = ['RedisCache', 'CogABCMeta']


class CogABCMeta(CogMeta, ABCMeta):
    """Metaclass for ABCs meant to be implemented as Cogs."""

    pass
