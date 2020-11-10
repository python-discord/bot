from typing import Optional

from async_rediscache.types.base import RedisObject, namespace_lock


class DocRedisCache(RedisObject):
    """Interface for redis functionality needed by the Doc cog."""

    @namespace_lock
    async def set(self, key: str, value: str) -> None:
        """
        Set markdown `value` for `key`.

        Keys expire after a week to keep data up to date.
        """
        with await self._get_pool_connection() as connection:
            await connection.setex(f"{self.namespace}:{key}", 7*24*60*60, value)

    @namespace_lock
    async def get(self, key: str) -> Optional[str]:
        """Get markdown contents for `key`."""
        with await self._get_pool_connection() as connection:
            return await connection.get(f"{self.namespace}:{key}", encoding="utf8")
