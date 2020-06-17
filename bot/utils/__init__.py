from abc import ABCMeta

from discord.ext.commands import CogMeta

from bot.utils.redis_cache import RedisCache

__all__ = ['RedisCache', 'CogABCMeta']


class CogABCMeta(CogMeta, ABCMeta):
    """Metaclass for ABCs meant to be implemented as Cogs."""

    pass


def pad_base64(data: str) -> str:
    """Return base64 `data` with padding characters to ensure its length is a multiple of 4."""
    return data + "=" * (-len(data) % 4)
