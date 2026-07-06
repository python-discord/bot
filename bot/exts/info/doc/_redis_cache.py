import datetime
import fnmatch
import time

from async_rediscache.types.base import RedisObject

from bot.log import get_logger
from bot.utils.lock import lock

from ._doc_item import DocItem

WEEK_SECONDS = int(datetime.timedelta(weeks=1).total_seconds())

log = get_logger(__name__)


def serialize_resource_id_from_doc_item(bound_args: dict) -> str:
    """Return the redis_key of the DocItem `item` from the bound args of DocRedisCache.set."""
    item: DocItem = bound_args["item"]
    return f"doc:{item_key(item)}"


class DocRedisCache(RedisObject):
    """Interface for redis functionality needed by the Doc cog."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._set_expires = dict[str, float]()

    @lock("DocRedisCache.set", serialize_resource_id_from_doc_item, wait=True)
    async def set(self, item: DocItem, value: str) -> None:
        """
        Set the Markdown `value` for the symbol `item`.

        All keys from a single page are stored together, expiring a week after the first set.
        """
        redis_key = f"{self.namespace}:{item_key(item)}"
        needs_expire = False

        set_expire = self._set_expires.get(redis_key)
        if set_expire is None:
            # An expire is only set if the key didn't exist before.
            ttl = await self.redis_session.client.ttl(redis_key)
            log.debug("Checked TTL for `%s`.", redis_key)

            if ttl == -1:
                log.warning("Key `%s` had no expire set.", redis_key)
            if ttl < 0:  # not set or didn't exist
                needs_expire = True
            else:
                log.debug("Key `%s` has a %s TTL.", redis_key, ttl)
                self._set_expires[redis_key] = time.monotonic() + ttl - .1  # we need this to expire before redis

        elif time.monotonic() > set_expire:
            # If we got here the key expired in redis and we can be sure it doesn't exist.
            needs_expire = True
            log.debug("Key `%s` expired in internal key cache.", redis_key)

        await self.redis_session.client.hset(redis_key, item.symbol_id, value)
        if needs_expire:
            self._set_expires[redis_key] = time.monotonic() + WEEK_SECONDS
            await self.redis_session.client.expire(redis_key, WEEK_SECONDS)
            log.info("Set %s to expire in a week.", redis_key)

    async def get(self, item: DocItem) -> str | None:
        """Return the Markdown content of the symbol `item` if it exists."""
        return await self.redis_session.client.hget(f"{self.namespace}:{item_key(item)}", item.symbol_id)

    async def delete(self, package: str) -> bool:
        """Remove all values for `package`; return True if at least one key was deleted, False otherwise."""
        pattern = f"{self.namespace}:{package}:*"

        package_keys = [
            package_key async for package_key in self.redis_session.client.scan_iter(match=pattern)
        ]
        if package_keys:
            await self.redis_session.client.delete(*package_keys)
            log.info("Deleted keys from redis: %s.", package_keys)
            self._set_expires = {
                key: expire for key, expire in self._set_expires.items() if not fnmatch.fnmatchcase(key, pattern)
            }
            return True
        return False


class StaleItemCounter(RedisObject):
    """Manage increment counters for stale `DocItem`s."""

    async def increment_for(self, item: DocItem) -> int:
        """
        Increment the counter for `item` by 1, set it to expire in 3 weeks and return the new value.

        If the counter didn't exist, initialize it with 1.
        """
        key = f"{self.namespace}:{item_key(item)}:{item.symbol_id}"
        await self.redis_session.client.expire(key, WEEK_SECONDS * 3)
        return int(await self.redis_session.client.incr(key))

    async def delete(self, package: str) -> bool:
        """Remove all values for `package`; return True if at least one key was deleted, False otherwise."""
        package_keys = [
            package_key
            async for package_key in self.redis_session.client.scan_iter(match=f"{self.namespace}:{package}:*")
        ]
        if package_keys:
            await self.redis_session.client.delete(*package_keys)
            return True
        return False


def item_key(item: DocItem) -> str:
    """Get the redis redis key string from `item`."""
    return f"{item.package}:{item.relative_url_path.removesuffix('.html')}"
