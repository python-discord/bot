from __future__ import annotations

from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, Union

from bot.bot import Bot

ValidRedisKey = Union[str, int, float]
JSONSerializableType = Optional[Union[str, float, bool, Dict, List, Tuple, Enum]]


class RedisCache:
    """
    A simplified interface for a Redis connection.

    This class must be created as a class attribute in a class. This is because it
    uses __set_name__ to create a namespace like MyCog.my_class_attribute which is
    used as a hash name when we store stuff in Redis, to prevent collisions.

    The class this object is instantiated in must also contains an attribute with an
    instance of Bot. This is because Bot contains our redis_pool, which is how this
    class communicates with the Redis server.

    We implement several convenient methods that are fairly similar to have a dict
    behaves, and should be familiar to Python users. The biggest difference is that
    all the public methods in this class are coroutines.
    """

    _namespaces = []

    def __init__(self) -> None:
        """Raise a NotImplementedError if `__set_name__` hasn't been run."""
        self._namespace = None
        self.bot = None

    def _set_namespace(self, namespace: str) -> None:
        """Try to set the namespace, but do not permit collisions."""
        while namespace in self._namespaces:
            namespace += "_"

        self._namespaces.append(namespace)
        self._namespace = namespace

    def __set_name__(self, owner: object, attribute_name: str) -> None:
        """
        Set the namespace to Class.attribute_name.

        Called automatically when this class is constructed inside a class as an attribute.
        """
        self._set_namespace(f"{owner.__name__}.{attribute_name}")

    def __get__(self, instance: RedisCache, owner: Any) -> RedisCache:
        """Fetch the Bot instance, we need it for the redis pool."""
        if self.bot:
            return self

        if instance is None:
            raise NotImplementedError("You must create an instance of RedisCache to use it.")

        for attribute in vars(instance).values():
            if isinstance(attribute, Bot):
                self.bot = attribute
                self._redis = self.bot.redis_session
                return self
        else:
            raise RuntimeError("Cannot initialize a RedisCache without a `Bot` instance.")

    def __repr__(self) -> str:
        """Return a beautiful representation of this object instance."""
        return f"RedisCache(namespace={self._namespace!r})"

    async def set(self, key: ValidRedisKey, value: JSONSerializableType) -> None:
        """Store an item in the Redis cache."""
        # await self._redis.hset(self._namespace, key, value)

    async def get(self, key: ValidRedisKey, default: Optional[JSONSerializableType] = None) -> JSONSerializableType:
        """Get an item from the Redis cache."""
        # value = await self._redis.hget(self._namespace, key)

    async def delete(self, key: ValidRedisKey) -> None:
        """Delete an item from the Redis cache."""
        # await self._redis.hdel(self._namespace, key)

    async def contains(self, key: ValidRedisKey) -> bool:
        """Check if a key exists in the Redis cache."""
        # return await self._redis.hexists(self._namespace, key)

    async def items(self) -> AsyncIterator:
        """Iterate all the items in the Redis cache."""
        # data = await redis.hgetall(self.get_with_namespace(key))
        # for item in data:
        #     yield item

    async def length(self) -> int:
        """Return the number of items in the Redis cache."""
        # return await self._redis.hlen(self._namespace)

    async def to_dict(self) -> Dict:
        """Convert to dict and return."""
        # return dict(self.items())

    async def clear(self) -> None:
        """Deletes the entire hash from the Redis cache."""
        # await self._redis.delete(self._namespace)

    async def pop(self, key: ValidRedisKey, default: Optional[JSONSerializableType] = None) -> JSONSerializableType:
        """Get the item, remove it from the cache, and provide a default if not found."""
        # value = await self.get(key, default)
        # await self.delete(key)
        # return value

    async def update(self) -> None:
        """Update the Redis cache with multiple values."""
        # https://aioredis.readthedocs.io/en/v1.3.0/mixins.html#aioredis.commands.HashCommandsMixin.hmset_dict
