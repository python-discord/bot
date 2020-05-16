import json
from collections.abc import MutableMapping
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

import redis as redis_py

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
    _redis = redis_py.Redis(host="redis")  # Can be overridden for testing

    def __init__(self, namespace: Optional[str] = None) -> None:
        """Initialize the RedisDict with the right namespace."""
        super().__init__()
        self._has_custom_namespace = namespace is not None
        self._set_namespace(namespace)

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

    def __setitem__(self, key: ValidRedisKey, value: JSONSerializableType):
        """Store an item in the Redis cache."""
        # JSON serialize the value before storing it.
        json_value = json.dumps(value)
        self._redis.hset(self._namespace, key, json_value)

    def __getitem__(self, key: ValidRedisKey):
        """Get an item from the Redis cache."""
        value = self._redis.hget(self._namespace, key)
        return json.loads(value)

    def __delitem__(self, key: ValidRedisKey):
        """Delete an item from the Redis cache."""
        self._redis.hdel(self._namespace, key)

    def __iter__(self):
        """Iterate all the items in the Redis cache."""
        return iter(self._redis.hkeys(self._namespace))

    def __len__(self):
        """Return the number of items in the Redis cache."""
        return self._redis.hlen(self._namespace)

    def copy(self) -> Dict:
        """Convert to dict and return."""
        return dict(self.items())
