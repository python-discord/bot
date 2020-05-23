from __future__ import annotations

from typing import Any, AsyncIterator, Dict, Optional, Union

from bot.bot import Bot

TYPESTRING_PREFIXES = (
    ("f|", float),
    ("i|", int),
    ("s|", str),
)
ValidRedisType = Union[str, int, float]


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
    all the public methods in this class are coroutines, and must be awaited.

    Because of limitations in Redis, this cache will only accept strings, integers and
    floats both for keys and values.

    Simple example for how to use this:

    class SomeCog(Cog):
        # To initialize a valid RedisCache, just add it as a class attribute here.
        # Do not add it to the __init__ method or anywhere else, it MUST be a class
        # attribute. Do not pass any parameters.
        cache = RedisCache()

        async def my_method(self):

            # Now we're ready to use the RedisCache.
            # One thing to note here is that this will not work unless
            # we access self.cache through an _instance_ of this class.
            #
            # For example, attempting to use SomeCog.cache will _not_ work,
            # you _must_ instantiate the class first and use that instance.
            #
            # Now we can store some stuff in the cache just by doing this.
            # This data will persist through restarts!
            await self.cache.set("key", "value")

            # To get the data, simply do this.
            value = await self.cache.get("key")

            # Other methods work more or less like a dictionary.
            # Checking if something is in the cache
            await self.cache.contains("key")

            # iterating the cache
            async for key, value in self.cache.items():
                print(value)

            # We can even iterate in a comprehension!
            consumed = [value async for key, value in self.cache.items()]
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

    @staticmethod
    def _valid_typestring_types() -> str:
        """
        Creates a nice, readable list of valid types for typestrings, useful for error messages.

        This will be dynamically updated if we change the TYPESTRING_PREFIXES constant up top.
        """
        valid_types = ", ".join([str(_type).split("'")[1] for _, _type in TYPESTRING_PREFIXES])
        valid_types = ", and ".join(valid_types.rsplit(", ", 1))
        return valid_types

    @staticmethod
    def _valid_typestring_prefixes() -> str:
        """
        Creates a nice, readable list of valid prefixes for typestrings, useful for error messages.

        This will be dynamically updated if we change the TYPESTRING_PREFIXES constant up top.
        """
        valid_prefixes = ", ".join([f"'{prefix}'" for prefix, _ in TYPESTRING_PREFIXES])
        valid_prefixes = ", and ".join(valid_prefixes.rsplit(", ", 1))
        return valid_prefixes

    def _to_typestring(self, value: ValidRedisType) -> str:
        """Turn a valid Redis type into a typestring."""
        for prefix, _type in TYPESTRING_PREFIXES:
            if isinstance(value, _type):
                return f"{prefix}{value}"
        raise TypeError(f"RedisCache._from_typestring only supports the types {self._valid_typestring_types()}.")

    def _from_typestring(self, value: Union[bytes, str]) -> ValidRedisType:
        """Turn a typestring into a valid Redis type."""
        # Stuff that comes out of Redis will be bytestrings, so let's decode those.
        if isinstance(value, bytes):
            value = value.decode('utf-8')

        # Now we convert our unicode string back into the type it originally was.
        for prefix, _type in TYPESTRING_PREFIXES:
            if value.startswith(prefix):
                return _type(value[2:])
        raise TypeError(f"RedisCache._to_typestring only supports the prefixes {self._valid_typestring_prefixes()}.")

    def _dict_from_typestring(self, dictionary: Dict) -> Dict:
        """Turns all contents of a dict into valid Redis types."""
        return {self._from_typestring(key): self._from_typestring(value) for key, value in dictionary.items()}

    def _dict_to_typestring(self, dictionary: Dict) -> Dict:
        """Turns all contents of a dict into typestrings."""
        return {self._to_typestring(key): self._to_typestring(value) for key, value in dictionary.items()}

    async def _validate_cache(self) -> None:
        """Validate that the RedisCache is ready to be used."""
        if self.bot is None:
            raise RuntimeError("Critical error: RedisCache has no `Bot` instance.")

        if self._namespace is None:
            raise RuntimeError(
                "Critical error: RedisCache has no namespace. "
                "Did you initialize this object as a class attribute?"
            )
        await self.bot._redis_ready.wait()

    def __set_name__(self, owner: Any, attribute_name: str) -> None:
        """
        Set the namespace to Class.attribute_name.

        Called automatically when this class is constructed inside a class as an attribute.
        """
        self._set_namespace(f"{owner.__name__}.{attribute_name}")

    def __get__(self, instance: RedisCache, owner: Any) -> RedisCache:
        """Fetch the Bot instance, we need it for the redis pool."""
        if self.bot:
            return self

        if self._namespace is None:
            raise RuntimeError("RedisCache must be a class attribute.")

        if instance is None:
            raise RuntimeError(
                "You must access the RedisCache instance through the cog instance "
                "before accessing it using the cog's class object."
            )

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

    async def set(self, key: ValidRedisType, value: ValidRedisType) -> None:
        """Store an item in the Redis cache."""
        await self._validate_cache()

        # Convert to a typestring and then set it
        key = self._to_typestring(key)
        value = self._to_typestring(value)
        await self._redis.hset(self._namespace, key, value)

    async def get(self, key: ValidRedisType, default: Optional[ValidRedisType] = None) -> ValidRedisType:
        """Get an item from the Redis cache."""
        await self._validate_cache()
        key = self._to_typestring(key)
        value = await self._redis.hget(self._namespace, key)

        if value is None:
            return default
        else:
            value = self._from_typestring(value)
            return value

    async def delete(self, key: ValidRedisType) -> None:
        """
        Delete an item from the Redis cache.

        If we try to delete a key that does not exist, it will simply be ignored.

        See https://redis.io/commands/hdel for more info on how this works.
        """
        await self._validate_cache()
        key = self._to_typestring(key)
        return await self._redis.hdel(self._namespace, key)

    async def contains(self, key: ValidRedisType) -> bool:
        """
        Check if a key exists in the Redis cache.

        Return True if the key exists, otherwise False.
        """
        await self._validate_cache()
        key = self._to_typestring(key)
        return await self._redis.hexists(self._namespace, key)

    async def items(self) -> AsyncIterator:
        """Iterate all the items in the Redis cache."""
        await self._validate_cache()
        data = await self._redis.hgetall(self._namespace)  # Get all the keys
        for key, value in self._dict_from_typestring(data).items():
            yield key, value

    async def length(self) -> int:
        """Return the number of items in the Redis cache."""
        await self._validate_cache()
        return await self._redis.hlen(self._namespace)

    async def to_dict(self) -> Dict:
        """Convert to dict and return."""
        return {key: value async for key, value in self.items()}

    async def clear(self) -> None:
        """Deletes the entire hash from the Redis cache."""
        await self._validate_cache()
        await self._redis.delete(self._namespace)

    async def pop(self, key: ValidRedisType, default: Optional[ValidRedisType] = None) -> ValidRedisType:
        """Get the item, remove it from the cache, and provide a default if not found."""
        value = await self.get(key, default)

        # No need to try to delete something that doesn't exist,
        # that's just a superfluous API call.
        if value != default:
            await self.delete(key)

        return value

    async def update(self, items: Dict) -> None:
        """Update the Redis cache with multiple values."""
        await self._validate_cache()
        await self._redis.hmset_dict(self._namespace, self._dict_to_typestring(items))
