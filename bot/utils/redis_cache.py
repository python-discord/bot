from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, ItemsView, Optional, Union

from bot.bot import Bot

log = logging.getLogger(__name__)

RedisType = Union[str, int, float]
TYPESTRING_PREFIXES = (
    ("f|", float),
    ("i|", int),
    ("s|", str),
)

# Makes a nice list like "float, int, and str"
NICE_TYPE_LIST = ", ".join(str(_type.__name__) for _, _type in TYPESTRING_PREFIXES)
NICE_TYPE_LIST = ", and ".join(NICE_TYPE_LIST.rsplit(", ", 1))

# Makes a list like "'f|', 'i|', and 's|'"
NICE_PREFIX_LIST = ", ".join([f"'{prefix}'" for prefix, _ in TYPESTRING_PREFIXES])
NICE_PREFIX_LIST = ", and ".join(NICE_PREFIX_LIST.rsplit(", ", 1))


class RedisCache:
    """
    A simplified interface for a Redis connection.

    We implement several convenient methods that are fairly similar to have a dict
    behaves, and should be familiar to Python users. The biggest difference is that
    all the public methods in this class are coroutines, and must be awaited.

    Because of limitations in Redis, this cache will only accept strings, integers and
    floats both for keys and values.

    Please note that this class MUST be created as a class attribute, and that that class
    must also contain an attribute with an instance of our Bot. See `__get__` and `__set_name__`
    for more information about how this works.

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
        """Initialize the RedisCache."""
        self._namespace = None
        self.bot = None
        self._increment_lock = asyncio.Lock()

    def _set_namespace(self, namespace: str) -> None:
        """Try to set the namespace, but do not permit collisions."""
        # We need a unique namespace, to prevent collisions. This loop
        # will try appending underscores to the end of the namespace until
        # it finds one that is unique.
        #
        # For example, if `john` and `john_`  are both taken, the namespace will
        # be `john__` at the end of this loop.
        while namespace in self._namespaces:
            namespace += "_"

        log.trace(f"RedisCache setting namespace to {self._namespace}")
        self._namespaces.append(namespace)
        self._namespace = namespace

    @staticmethod
    def _to_typestring(value: RedisType) -> str:
        """Turn a valid Redis type into a typestring."""
        for prefix, _type in TYPESTRING_PREFIXES:
            if isinstance(value, _type):
                return f"{prefix}{value}"
        raise TypeError(f"RedisCache._from_typestring only supports the types {NICE_TYPE_LIST}.")

    @staticmethod
    def _from_typestring(value: Union[bytes, str]) -> RedisType:
        """Turn a typestring into a valid Redis type."""
        # Stuff that comes out of Redis will be bytestrings, so let's decode those.
        if isinstance(value, bytes):
            value = value.decode('utf-8')

        # Now we convert our unicode string back into the type it originally was.
        for prefix, _type in TYPESTRING_PREFIXES:
            if value.startswith(prefix):
                return _type(value[len(prefix):])
        raise TypeError(f"RedisCache._to_typestring only supports the prefixes {NICE_PREFIX_LIST}.")

    def _dict_from_typestring(self, dictionary: Dict) -> Dict:
        """Turns all contents of a dict into valid Redis types."""
        return {self._from_typestring(key): self._from_typestring(value) for key, value in dictionary.items()}

    def _dict_to_typestring(self, dictionary: Dict) -> Dict:
        """Turns all contents of a dict into typestrings."""
        return {self._to_typestring(key): self._to_typestring(value) for key, value in dictionary.items()}

    async def _validate_cache(self) -> None:
        """Validate that the RedisCache is ready to be used."""
        if self.bot is None:
            error_message = (
                "Critical error: RedisCache has no `Bot` instance. "
                "This happens when the class RedisCache was created in doesn't "
                "have a Bot instance. Please make sure that you're instantiating "
                "the RedisCache inside a class that has a Bot instance "
                "class attribute."
            )
            log.error(error_message)
            raise RuntimeError(error_message)

        if self._namespace is None:
            error_message = (
                "Critical error: RedisCache has no namespace. "
                "Did you initialize this object as a class attribute?"
            )
            log.error(error_message)
            raise RuntimeError(error_message)

        await self.bot.redis_ready.wait()

    def __set_name__(self, owner: Any, attribute_name: str) -> None:
        """
        Set the namespace to Class.attribute_name.

        Called automatically when this class is constructed inside a class as an attribute.

        This class MUST be created as a class attribute in a class, otherwise it will raise
        exceptions whenever a method is used. This is because it uses this method to create
        a namespace like `MyCog.my_class_attribute` which is used as a hash name when we store
        stuff in Redis, to prevent collisions.
        """
        self._set_namespace(f"{owner.__name__}.{attribute_name}")

    def __get__(self, instance: RedisCache, owner: Any) -> RedisCache:
        """
        This is called if the RedisCache is a class attribute, and is accessed.

        The class this object is instantiated in must contain an attribute with an
        instance of Bot. This is because Bot contains our redis_session, which is
        the mechanism by which we will communicate with the Redis server.

        Any attempt to use RedisCache in a class that does not have a Bot instance
        will fail. It is mostly intended to be used inside of a Cog, although theoretically
        it should work in any class that has a Bot instance.
        """
        if self.bot:
            return self

        if self._namespace is None:
            error_message = "RedisCache must be a class attribute."
            log.error(error_message)
            raise RuntimeError(error_message)

        if instance is None:
            error_message = (
                "You must access the RedisCache instance through the cog instance "
                "before accessing it using the cog's class object."
            )
            log.error(error_message)
            raise RuntimeError(error_message)

        for attribute in vars(instance).values():
            if isinstance(attribute, Bot):
                self.bot = attribute
                self._redis = self.bot.redis_session
                return self
        else:
            error_message = (
                "Critical error: RedisCache has no `Bot` instance. "
                "This happens when the class RedisCache was created in doesn't "
                "have a Bot instance. Please make sure that you're instantiating "
                "the RedisCache inside a class that has a Bot instance "
                "class attribute."
            )
            log.error(error_message)
            raise RuntimeError(error_message)

    def __repr__(self) -> str:
        """Return a beautiful representation of this object instance."""
        return f"RedisCache(namespace={self._namespace!r})"

    async def set(self, key: RedisType, value: RedisType) -> None:
        """Store an item in the Redis cache."""
        await self._validate_cache()

        # Convert to a typestring and then set it
        key = self._to_typestring(key)
        value = self._to_typestring(value)

        log.trace(f"Setting {key} to {value}.")
        await self._redis.hset(self._namespace, key, value)

    async def get(self, key: RedisType, default: Optional[RedisType] = None) -> Optional[RedisType]:
        """Get an item from the Redis cache."""
        await self._validate_cache()
        key = self._to_typestring(key)

        log.trace(f"Attempting to retrieve {key}.")
        value = await self._redis.hget(self._namespace, key)

        if value is None:
            log.trace(f"Value not found, returning default value {default}")
            return default
        else:
            value = self._from_typestring(value)
            log.trace(f"Value found, returning value {value}")
            return value

    async def delete(self, key: RedisType) -> None:
        """
        Delete an item from the Redis cache.

        If we try to delete a key that does not exist, it will simply be ignored.

        See https://redis.io/commands/hdel for more info on how this works.
        """
        await self._validate_cache()
        key = self._to_typestring(key)

        log.trace(f"Attempting to delete {key}.")
        return await self._redis.hdel(self._namespace, key)

    async def contains(self, key: RedisType) -> bool:
        """
        Check if a key exists in the Redis cache.

        Return True if the key exists, otherwise False.
        """
        await self._validate_cache()
        key = self._to_typestring(key)
        exists = await self._redis.hexists(self._namespace, key)

        log.trace(f"Testing if {key} exists in the RedisCache - Result is {exists}")
        return exists

    async def items(self) -> ItemsView:
        """
        Fetch all the key/value pairs in the cache.

        Returns a normal ItemsView, like you would get from dict.items().

        Keep in mind that these items are just a _copy_ of the data in the
        RedisCache - any changes you make to them will not be reflected
        into the RedisCache itself. If you want to change these, you need
        to make a .set call.

        Example:
        items = await my_cache.items()
        for key, value in items:
            # Iterate like a normal dictionary
        """
        await self._validate_cache()
        items = self._dict_from_typestring(
            await self._redis.hgetall(self._namespace)
        ).items()

        log.trace(f"Retrieving all key/value pairs from cache, total of {len(items)} items.")
        return items

    async def length(self) -> int:
        """Return the number of items in the Redis cache."""
        await self._validate_cache()
        number_of_items = await self._redis.hlen(self._namespace)
        log.trace(f"Returning length. Result is {number_of_items}.")
        return number_of_items

    async def to_dict(self) -> Dict:
        """Convert to dict and return."""
        return {key: value for key, value in await self.items()}

    async def clear(self) -> None:
        """Deletes the entire hash from the Redis cache."""
        await self._validate_cache()
        log.trace("Clearing the cache of all key/value pairs.")
        await self._redis.delete(self._namespace)

    async def pop(self, key: RedisType, default: Optional[RedisType] = None) -> RedisType:
        """Get the item, remove it from the cache, and provide a default if not found."""
        log.trace(f"Attempting to pop {key}.")
        value = await self.get(key, default)

        log.trace(
            f"Attempting to delete item with key '{key}' from the cache. "
            "If this key doesn't exist, nothing will happen."
        )
        await self.delete(key)

        return value

    async def update(self, items: Dict[RedisType, RedisType]) -> None:
        """
        Update the Redis cache with multiple values.

        This works exactly like dict.update from a normal dictionary. You pass
        a dictionary with one or more key/value pairs into this method. If the keys
        do not exist in the RedisCache, they are created. If they do exist, the values
        are updated with the new ones from `items`.

        Please note that both the keys and the values in the `items` dictionary
        must consist of valid RedisTypes - ints, floats, or strings.
        """
        await self._validate_cache()
        log.trace(f"Updating the cache with the following items:\n{items}")
        await self._redis.hmset_dict(self._namespace, self._dict_to_typestring(items))

    async def increment(self, key: RedisType, amount: Optional[int, float] = 1) -> None:
        """
        Increment the value by `amount`.

        This works for both floats and ints, but will raise a TypeError
        if you try to do it for any other type of value.

        This also supports negative amounts, although it would provide better
        readability to use .decrement() for that.
        """
        log.trace(f"Attempting to increment/decrement the value with the key {key} by {amount}.")

        # Since this has several API calls, we need a lock to prevent race conditions
        async with self._increment_lock:
            value = await self.get(key)

            # Can't increment a non-existing value
            if value is None:
                error_message = "The provided key does not exist!"
                log.error(error_message)
                raise KeyError(error_message)

            # If it does exist, and it's an int or a float, increment and set it.
            if isinstance(value, int) or isinstance(value, float):
                value += amount
                await self.set(key, value)
            else:
                error_message = "You may only increment or decrement values that are integers or floats."
                log.error(error_message)
                raise TypeError(error_message)

    async def decrement(self, key: RedisType, amount: Optional[int, float] = 1) -> None:
        """
        Decrement the value by `amount`.

        Basically just does the opposite of .increment.
        """
        await self.increment(key, -amount)
