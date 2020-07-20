from __future__ import annotations

import asyncio
import logging
from functools import partialmethod
from typing import Any, Dict, ItemsView, Optional, Tuple, Union

from bot.bot import Bot

log = logging.getLogger(__name__)

# Type aliases
RedisKeyType = Union[str, int]
RedisValueType = Union[str, int, float, bool]
RedisKeyOrValue = Union[RedisKeyType, RedisValueType]

# Prefix tuples
_PrefixTuple = Tuple[Tuple[str, Any], ...]
_VALUE_PREFIXES = (
    ("f|", float),
    ("i|", int),
    ("s|", str),
    ("b|", bool),
)
_KEY_PREFIXES = (
    ("i|", int),
    ("s|", str),
)


class NoBotInstanceError(RuntimeError):
    """Raised when RedisCache is created without an available bot instance on the owner class."""


class NoNamespaceError(RuntimeError):
    """Raised when RedisCache has no namespace, for example if it is not assigned to a class attribute."""


class NoParentInstanceError(RuntimeError):
    """Raised when the parent instance is available, for example if called by accessing the parent class directly."""


class RedisCache:
    """
    A simplified interface for a Redis connection.

    We implement several convenient methods that are fairly similar to have a dict
    behaves, and should be familiar to Python users. The biggest difference is that
    all the public methods in this class are coroutines, and must be awaited.

    Because of limitations in Redis, this cache will only accept strings and integers for keys,
    and strings, integers, floats and booleans for values.

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
        self._increment_lock = None

    def _set_namespace(self, namespace: str) -> None:
        """Try to set the namespace, but do not permit collisions."""
        log.trace(f"RedisCache setting namespace to {namespace}")
        self._namespaces.append(namespace)
        self._namespace = namespace

    @staticmethod
    def _to_typestring(key_or_value: RedisKeyOrValue, prefixes: _PrefixTuple) -> str:
        """Turn a valid Redis type into a typestring."""
        for prefix, _type in prefixes:
            # Convert bools into integers before storing them.
            if type(key_or_value) is bool:
                bool_int = int(key_or_value)
                return f"{prefix}{bool_int}"

            # isinstance is a bad idea here, because isintance(False, int) == True.
            if type(key_or_value) is _type:
                return f"{prefix}{key_or_value}"

        raise TypeError(f"RedisCache._to_typestring only supports the following: {prefixes}.")

    @staticmethod
    def _from_typestring(key_or_value: Union[bytes, str], prefixes: _PrefixTuple) -> RedisKeyOrValue:
        """Deserialize a typestring into a valid Redis type."""
        # Stuff that comes out of Redis will be bytestrings, so let's decode those.
        if isinstance(key_or_value, bytes):
            key_or_value = key_or_value.decode('utf-8')

        # Now we convert our unicode string back into the type it originally was.
        for prefix, _type in prefixes:
            if key_or_value.startswith(prefix):

                # For booleans, we need special handling because bool("False") is True.
                if prefix == "b|":
                    value = key_or_value[len(prefix):]
                    return bool(int(value))

                # Otherwise we can just convert normally.
                return _type(key_or_value[len(prefix):])
        raise TypeError(f"RedisCache._from_typestring only supports the following: {prefixes}.")

    # Add some nice partials to call our generic typestring converters.
    # These are basically methods that will fill in some of the parameters for you, so that
    # any call to _key_to_typestring will be like calling _to_typestring with the two parameters
    # at `prefixes` and `types_string` pre-filled.
    #
    # See https://docs.python.org/3/library/functools.html#functools.partialmethod
    _key_to_typestring = partialmethod(_to_typestring, prefixes=_KEY_PREFIXES)
    _value_to_typestring = partialmethod(_to_typestring, prefixes=_VALUE_PREFIXES)
    _key_from_typestring = partialmethod(_from_typestring, prefixes=_KEY_PREFIXES)
    _value_from_typestring = partialmethod(_from_typestring, prefixes=_VALUE_PREFIXES)

    def _dict_from_typestring(self, dictionary: Dict) -> Dict:
        """Turns all contents of a dict into valid Redis types."""
        return {self._key_from_typestring(key): self._value_from_typestring(value) for key, value in dictionary.items()}

    def _dict_to_typestring(self, dictionary: Dict) -> Dict:
        """Turns all contents of a dict into typestrings."""
        return {self._key_to_typestring(key): self._value_to_typestring(value) for key, value in dictionary.items()}

    async def _validate_cache(self) -> None:
        """Validate that the RedisCache is ready to be used."""
        if self._namespace is None:
            error_message = (
                "Critical error: RedisCache has no namespace. "
                "This object must be initialized as a class attribute."
            )
            log.error(error_message)
            raise NoNamespaceError(error_message)

        if self.bot is None:
            error_message = (
                "Critical error: RedisCache has no `Bot` instance. "
                "This happens when the class RedisCache was created in doesn't "
                "have a Bot instance. Please make sure that you're instantiating "
                "the RedisCache inside a class that has a Bot instance attribute."
            )
            log.error(error_message)
            raise NoBotInstanceError(error_message)

        if not self.bot.redis_closed:
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
            raise NoNamespaceError(error_message)

        if instance is None:
            error_message = (
                "You must access the RedisCache instance through the cog instance "
                "before accessing it using the cog's class object."
            )
            log.error(error_message)
            raise NoParentInstanceError(error_message)

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
                "the RedisCache inside a class that has a Bot instance attribute."
            )
            log.error(error_message)
            raise NoBotInstanceError(error_message)

    def __repr__(self) -> str:
        """Return a beautiful representation of this object instance."""
        return f"RedisCache(namespace={self._namespace!r})"

    async def set(self, key: RedisKeyType, value: RedisValueType) -> None:
        """Store an item in the Redis cache."""
        await self._validate_cache()

        # Convert to a typestring and then set it
        key = self._key_to_typestring(key)
        value = self._value_to_typestring(value)

        log.trace(f"Setting {key} to {value}.")
        await self._redis.hset(self._namespace, key, value)

    async def get(self, key: RedisKeyType, default: Optional[RedisValueType] = None) -> Optional[RedisValueType]:
        """Get an item from the Redis cache."""
        await self._validate_cache()
        key = self._key_to_typestring(key)

        log.trace(f"Attempting to retrieve {key}.")
        value = await self._redis.hget(self._namespace, key)

        if value is None:
            log.trace(f"Value not found, returning default value {default}")
            return default
        else:
            value = self._value_from_typestring(value)
            log.trace(f"Value found, returning value {value}")
            return value

    async def delete(self, key: RedisKeyType) -> None:
        """
        Delete an item from the Redis cache.

        If we try to delete a key that does not exist, it will simply be ignored.

        See https://redis.io/commands/hdel for more info on how this works.
        """
        await self._validate_cache()
        key = self._key_to_typestring(key)

        log.trace(f"Attempting to delete {key}.")
        return await self._redis.hdel(self._namespace, key)

    async def contains(self, key: RedisKeyType) -> bool:
        """
        Check if a key exists in the Redis cache.

        Return True if the key exists, otherwise False.
        """
        await self._validate_cache()
        key = self._key_to_typestring(key)
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

    async def pop(self, key: RedisKeyType, default: Optional[RedisValueType] = None) -> RedisValueType:
        """Get the item, remove it from the cache, and provide a default if not found."""
        log.trace(f"Attempting to pop {key}.")
        value = await self.get(key, default)

        log.trace(
            f"Attempting to delete item with key '{key}' from the cache. "
            "If this key doesn't exist, nothing will happen."
        )
        await self.delete(key)

        return value

    async def update(self, items: Dict[RedisKeyType, RedisValueType]) -> None:
        """
        Update the Redis cache with multiple values.

        This works exactly like dict.update from a normal dictionary. You pass
        a dictionary with one or more key/value pairs into this method. If the keys
        do not exist in the RedisCache, they are created. If they do exist, the values
        are updated with the new ones from `items`.

        Please note that keys and the values in the `items` dictionary
        must consist of valid RedisKeyTypes and RedisValueTypes.
        """
        await self._validate_cache()
        log.trace(f"Updating the cache with the following items:\n{items}")
        await self._redis.hmset_dict(self._namespace, self._dict_to_typestring(items))

    async def increment(self, key: RedisKeyType, amount: Optional[int, float] = 1) -> None:
        """
        Increment the value by `amount`.

        This works for both floats and ints, but will raise a TypeError
        if you try to do it for any other type of value.

        This also supports negative amounts, although it would provide better
        readability to use .decrement() for that.
        """
        log.trace(f"Attempting to increment/decrement the value with the key {key} by {amount}.")

        # We initialize the lock here, because we need to ensure we get it
        # running on the same loop as the calling coroutine.
        #
        # If we initialized the lock in the __init__, the loop that the coroutine this method
        # would be called from might not exist yet, and so the lock would be on a different
        # loop, which would raise RuntimeErrors.
        if self._increment_lock is None:
            self._increment_lock = asyncio.Lock()

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

    async def decrement(self, key: RedisKeyType, amount: Optional[int, float] = 1) -> None:
        """
        Decrement the value by `amount`.

        Basically just does the opposite of .increment.
        """
        await self.increment(key, -amount)
