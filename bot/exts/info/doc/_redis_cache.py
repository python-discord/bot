from __future__ import annotations

import datetime
from typing import Optional, TYPE_CHECKING

from async_rediscache.types.base import RedisObject, namespace_lock

if TYPE_CHECKING:
    from ._cog import DocItem

WEEK_SECONDS = datetime.timedelta(weeks=1).total_seconds()


class DocRedisCache(RedisObject):
    """Interface for redis functionality needed by the Doc cog."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._set_expires = set()

    @namespace_lock
    async def set(self, item: DocItem, value: str) -> None:
        """
        Set the Markdown `value` for the symbol `item`.

        All keys from a single page are stored together, expiring a week after the first set.
        """
        redis_key = f"{self.namespace}:{item_key(item)}"
        needs_expire = False

        with await self._get_pool_connection() as connection:
            if redis_key not in self._set_expires:
                # An expire is only set if the key didn't exist before.
                # If this is the first time setting values for this key check if it exists and add it to
                # `_set_expires` to prevent redundant checks for subsequent uses with items from the same page.
                self._set_expires.add(redis_key)
                needs_expire = not await connection.exists(redis_key)

            await connection.hset(redis_key, item.symbol_id, value)
            if needs_expire:
                await connection.expire(redis_key, WEEK_SECONDS)

    @namespace_lock
    async def get(self, item: DocItem) -> Optional[str]:
        """Return the Markdown content of the symbol `item` if it exists."""
        with await self._get_pool_connection() as connection:
            return await connection.hget(f"{self.namespace}:{item_key(item)}", item.symbol_id, encoding="utf8")

    @namespace_lock
    async def delete(self, package: str) -> bool:
        """Remove all values for `package`; return True if at least one key was deleted, False otherwise."""
        with await self._get_pool_connection() as connection:
            package_keys = [
                package_key async for package_key in connection.iscan(match=f"{self.namespace}:{package}:*")
            ]
            if package_keys:
                await connection.delete(*package_keys)
                return True
            return False


class StaleItemCounter(RedisObject):
    """Manage increment counters for stale `DocItem`s."""

    @namespace_lock
    async def increment_for(self, item: DocItem) -> int:
        """
        Increment the counter for `item` by 1, set it to expire in 3 weeks and return the new value.

        If the counter didn't exist, initialize it with 1.
        """
        key = f"{self.namespace}:{item_key(item)}:{item.symbol_id}"
        with await self._get_pool_connection() as connection:
            await connection.expire(key, WEEK_SECONDS * 3)
            return int(await connection.incr(key))

    @namespace_lock
    async def delete(self, package: str) -> bool:
        """Remove all values for `package`; return True if at least one key was deleted, False otherwise."""
        with await self._get_pool_connection() as connection:
            package_keys = [
                package_key async for package_key in connection.iscan(match=f"{self.namespace}:{package}:*")
            ]
            if package_keys:
                await connection.delete(*package_keys)
                return True
            return False


def item_key(item: DocItem) -> str:
    """Get the redis redis key string from `item`."""
    return f"{item.package}:{item.relative_url_path.removesuffix('.html')}"
