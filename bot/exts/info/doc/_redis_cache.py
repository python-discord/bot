from __future__ import annotations

import datetime
import pickle
from typing import Optional, TYPE_CHECKING

from async_rediscache.types.base import RedisObject, namespace_lock
if TYPE_CHECKING:
    from ._cog import DocItem


class DocRedisCache(RedisObject):
    """Interface for redis functionality needed by the Doc cog."""

    @namespace_lock
    async def set(self, item: DocItem, value: str) -> None:
        """
        Set markdown `value` for `key`.

        Keys expire after a week to keep data up to date.
        """
        expiry_timestamp = datetime.datetime.now().timestamp() + 7 * 24 * 60 * 60
        with await self._get_pool_connection() as connection:
            await connection.hset(
                f"{self.namespace}:{item.package}",
                self.get_item_key(item),
                pickle.dumps((value, expiry_timestamp))
            )

    @namespace_lock
    async def get(self, item: DocItem) -> Optional[str]:
        """Get markdown contents for `key`."""
        with await self._get_pool_connection() as connection:
            cached_value = await connection.hget(f"{self.namespace}:{item.package}", self.get_item_key(item))
            if cached_value is None:
                return None

            value, expire = pickle.loads(cached_value)
            if expire <= datetime.datetime.now().timestamp():
                await connection.hdel(f"{self.namespace}:{item.package}", self.get_item_key(item))
                return None

            return value

    @namespace_lock
    async def delete(self, package: str) -> None:
        """Remove all values for `package`."""
        with await self._get_pool_connection() as connection:
            await connection.delete(f"{self.namespace}:{package}")

    @namespace_lock
    async def delete_expired(self) -> None:
        """Delete all expired keys."""
        current_timestamp = datetime.datetime.now().timestamp()
        with await self._get_pool_connection() as connection:
            async for package_key in connection.iscan(match=f"{self.namespace}*"):
                expired_fields = []

                for field, cached_value in (await connection.hgetall(package_key)).items():
                    _, expire = pickle.loads(cached_value)
                    if expire <= current_timestamp:
                        expired_fields.append(field)

                if expired_fields:
                    await connection.hdel(package_key, *expired_fields)

    @staticmethod
    def get_item_key(item: DocItem) -> str:
        """Create redis key for `item`."""
        return item.relative_url_path + item.symbol_id
