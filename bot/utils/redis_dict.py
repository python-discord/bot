from __future__ import annotations

import json
from collections.abc import MutableMapping
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

import redis as redis_py

from bot import constants

ValidRedisKey = Union[str, int, float]
JSONSerializableType = Optional[Union[str, float, bool, Dict, List, Tuple, Enum]]


class RedisDict(MutableMapping):
    """
    A dictionary interface for a Redis database.

    Objects created by this class should mostly behave like a normal dictionary,
    but will store all the data in our Redis database for persistence between restarts.

    Redis is limited to simple types, so to allow you to store collections like lists
    and dictionaries, we JSON deserialize every value. That means that it will not be possible
    to store complex objects, only stuff like strings, numbers, and collections of strings and numbers.
    """

    _namespaces = []
    _redis = redis_py.Redis(
        host=constants.Bot.redis_host,
        port=constants.Bot.redis_port,
    )  # Can be overridden for testing

    def __init__(self, namespace: Optional[str] = None) -> None:
        """Initialize the RedisDict with the right namespace."""
        super().__init__()
        self._has_custom_namespace = namespace is not None

        if self._has_custom_namespace:
            self._set_namespace(namespace)
        else:
            self.namespace = "general"

    def _set_namespace(self, namespace: str) -> None:
        """Try to set the namespace, but do not permit collisions."""
        while namespace in self._namespaces:
            namespace = namespace + "_"

        self._namespaces.append(namespace)
        self._namespace = namespace

    def __set_name__(self, owner: object, attribute_name: str) -> None:
        """
        Set the namespace to Class.attribute_name.

        Called automatically when this class is constructed inside a class as an attribute, as long as
        no custom namespace is provided to the constructor.
        """
        if not self._has_custom_namespace:
            self._set_namespace(f"{owner.__name__}.{attribute_name}")

    def __repr__(self) -> str:
        """Return a beautiful representation of this object instance."""
        return f"RedisDict(namespace={self._namespace!r})"

    def __eq__(self, other: RedisDict) -> bool:
        """Check equality between two RedisDicts."""
        return self.items() == other.items() and self._namespace == other._namespace

    def __ne__(self, other: RedisDict) -> bool:
        """Check inequality between two RedisDicts."""
        return self.items() != other.items() or self._namespace != other._namespace

    def __setitem__(self, key: ValidRedisKey, value: JSONSerializableType):
        """Store an item in the Redis cache."""
        # JSON serialize the value before storing it.
        json_value = json.dumps(value)
        self._redis.hset(self._namespace, key, json_value)

    def __getitem__(self, key: ValidRedisKey):
        """Get an item from the Redis cache."""
        value = self._redis.hget(self._namespace, key)

        if value:
            return json.loads(value)

    def __delitem__(self, key: ValidRedisKey):
        """Delete an item from the Redis cache."""
        self._redis.hdel(self._namespace, key)

    def __contains__(self, key: ValidRedisKey):
        """Check if a key exists in the Redis cache."""
        return self._redis.hexists(self._namespace, key)

    def __iter__(self):
        """Iterate all the items in the Redis cache."""
        keys = self._redis.hkeys(self._namespace)
        return iter([key.decode('utf-8') for key in keys])

    def __len__(self):
        """Return the number of items in the Redis cache."""
        return self._redis.hlen(self._namespace)

    def copy(self) -> Dict:
        """Convert to dict and return."""
        return dict(self.items())

    def clear(self) -> None:
        """Deletes the entire hash from the Redis cache."""
        self._redis.delete(self._namespace)

    def get(self, key: ValidRedisKey, default: Optional[JSONSerializableType] = None) -> JSONSerializableType:
        """Get the item, but provide a default if not found."""
        if key in self:
            return self[key]
        else:
            return default

    def pop(self, key: ValidRedisKey, default: Optional[JSONSerializableType] = None) -> JSONSerializableType:
        """Get the item, remove it from the cache, and provide a default if not found."""
        value = self.get(key, default)
        del self[key]
        return value

    def popitem(self) -> JSONSerializableType:
        """Get the last item added to the cache."""
        key = list(self.keys())[-1]
        return self.pop(key)

    def setdefault(self, key: ValidRedisKey, default: Optional[JSONSerializableType] = None) -> JSONSerializableType:
        """Try to get the item. If the item does not exist, set it to `default` and return that."""
        value = self.get(key)

        if value is None:
            self[key] = default
            return default
