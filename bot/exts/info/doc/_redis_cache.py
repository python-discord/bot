from __future__ import annotations

import datetime
from typing import Optional, TYPE_CHECKING

from async_rediscache.types.base import RedisObject, namespace_lock
if TYPE_CHECKING:
    from ._cog import DocItem


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
        url_key = remove_suffix(item.relative_url_path, ".html")
        redis_key = f"{self.namespace}:{item.package}:{url_key}"
        needs_expire = False

        with await self._get_pool_connection() as connection:
            if item.package+url_key not in self._set_expires:
                self._set_expires.add(item.package+url_key)
                needs_expire = not await connection.exists(redis_key)

            await connection.hset(redis_key, item.symbol_id, value)
            if needs_expire:
                await connection.expire(redis_key, datetime.timedelta(weeks=1).total_seconds())

    @namespace_lock
    async def get(self, item: DocItem) -> Optional[str]:
        """Return the Markdown content of the symbol `item` if it exists."""
        url_key = remove_suffix(item.relative_url_path, ".html")

        with await self._get_pool_connection() as connection:
            return await connection.hget(f"{self.namespace}:{item.package}:{url_key}", item.symbol_id, encoding="utf8")

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


def remove_suffix(string: str, suffix: str) -> str:
    """Remove `suffix` from end of `string`."""
    # TODO replace usages with str.removesuffix on 3.9
    if string.endswith(suffix):
        return string[:-len(suffix)]
    else:
        return string
