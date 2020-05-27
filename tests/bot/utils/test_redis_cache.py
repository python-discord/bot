import unittest

import fakeredis.aioredis

from bot.utils import RedisCache
from tests import helpers


class RedisCacheTests(unittest.IsolatedAsyncioTestCase):
    """Tests the RedisCache class from utils.redis_dict.py."""

    redis = RedisCache()

    async def asyncSetUp(self):  # noqa: N802
        """Sets up the objects that only have to be initialized once."""
        self.bot = helpers.MockBot()
        self.bot.redis_session = await fakeredis.aioredis.create_redis_pool()
        await self.redis.clear()

    def test_class_attribute_namespace(self):
        """Test that RedisDict creates a namespace automatically for class attributes."""
        self.assertEqual(self.redis._namespace, "RedisCacheTests.redis")

    async def test_class_attribute_required(self):
        """Test that errors are raised when not assigned as a class attribute."""
        bad_cache = RedisCache()
        self.assertIs(bad_cache._namespace, None)

        with self.assertRaises(RuntimeError):
            await bad_cache.set("test", "me_up_deadman")

    def test_namespace_collision(self):
        """Test that we prevent colliding namespaces."""
        bad_cache = RedisCache()
        bad_cache._set_namespace("RedisCacheTests.redis")
        self.assertEqual(bad_cache._namespace, "RedisCacheTests.redis_")

    async def test_set_get_item(self):
        """Test that users can set and get items from the RedisDict."""
        test_cases = (
            ('favorite_fruit', 'melon'),
            ('favorite_number', 86),
            ('favorite_fraction', 86.54)
        )

        # Test that we can get and set different types.
        for test in test_cases:
            await self.redis.set(*test)
            self.assertEqual(await self.redis.get(test[0]), test[1])

        # Test that .get allows a default value
        self.assertEqual(await self.redis.get('favorite_nothing', "bearclaw"), "bearclaw")

    async def test_set_item_type(self):
        """Test that .set rejects keys and values that are not strings, ints or floats."""
        fruits = ["lemon", "melon", "apple"]

        with self.assertRaises(TypeError):
            await self.redis.set(fruits, "nice")

    async def test_delete_item(self):
        """Test that .delete allows us to delete stuff from the RedisCache."""
        # Add an item and verify that it gets added
        await self.redis.set("internet", "firetruck")
        self.assertEqual(await self.redis.get("internet"), "firetruck")

        # Delete that item and verify that it gets deleted
        await self.redis.delete("internet")
        self.assertIs(await self.redis.get("internet"), None)

    async def test_contains(self):
        """Test that we can check membership with .contains."""
        await self.redis.set('favorite_country', "Burkina Faso")

        self.assertIs(await self.redis.contains('favorite_country'), True)
        self.assertIs(await self.redis.contains('favorite_dentist'), False)

    async def test_items(self):
        """Test that the RedisDict can be iterated."""
        # Set up our test cases in the Redis cache
        test_cases = [
            ('favorite_turtle', 'Donatello'),
            ('second_favorite_turtle', 'Leonardo'),
            ('third_favorite_turtle', 'Raphael'),
        ]
        for key, value in test_cases:
            await self.redis.set(key, value)

        # Consume the AsyncIterator into a regular list, easier to compare that way.
        redis_items = [item for item in await self.redis.items()]

        # These sequences are probably in the same order now, but probably
        # isn't good enough for tests. Let's not rely on .hgetall always
        # returning things in sequence, and just sort both lists to be safe.
        redis_items = sorted(redis_items)
        test_cases = sorted(test_cases)

        # If these are equal now, everything works fine.
        self.assertSequenceEqual(test_cases, redis_items)

    async def test_length(self):
        """Test that we can get the correct .length from the RedisDict."""
        await self.redis.set('one', 1)
        await self.redis.set('two', 2)
        await self.redis.set('three', 3)
        self.assertEqual(await self.redis.length(), 3)

        await self.redis.set('four', 4)
        self.assertEqual(await self.redis.length(), 4)

    async def test_to_dict(self):
        """Test that the .to_dict method returns a workable dictionary copy."""
        copy = await self.redis.to_dict()
        local_copy = {key: value for key, value in await self.redis.items()}
        self.assertIs(type(copy), dict)
        self.assertDictEqual(copy, local_copy)

    async def test_clear(self):
        """Test that the .clear method removes the entire hash."""
        await self.redis.set('teddy', 'with me')
        await self.redis.set('in my dreams', 'you have a weird hat')
        self.assertEqual(await self.redis.length(), 2)

        await self.redis.clear()
        self.assertEqual(await self.redis.length(), 0)

    async def test_pop(self):
        """Test that we can .pop an item from the RedisDict."""
        await self.redis.set('john', 'was afraid')

        self.assertEqual(await self.redis.pop('john'), 'was afraid')
        self.assertEqual(await self.redis.pop('pete', 'breakneck'), 'breakneck')
        self.assertEqual(await self.redis.length(), 0)

    async def test_update(self):
        """Test that we can .update the RedisDict with multiple items."""
        await self.redis.set("reckfried", "lona")
        await self.redis.set("bel air", "prince")
        await self.redis.update({
            "reckfried": "jona",
            "mega": "hungry, though",
        })

        result = {
            "reckfried": "jona",
            "bel air": "prince",
            "mega": "hungry, though",
        }
        self.assertDictEqual(await self.redis.to_dict(), result)

    def test_typestring_conversion(self):
        """Test the typestring-related helper functions."""
        conversion_tests = (
            (12, "i|12"),
            (12.4, "f|12.4"),
            ("cowabunga", "s|cowabunga"),
        )

        # Test conversion to typestring
        for _input, expected in conversion_tests:
            self.assertEqual(self.redis._to_typestring(_input), expected)

        # Test conversion from typestrings
        for _input, expected in conversion_tests:
            self.assertEqual(self.redis._from_typestring(expected), _input)

        # Test that exceptions are raised on invalid input
        with self.assertRaises(TypeError):
            self.redis._to_typestring(["internet"])
            self.redis._from_typestring("o|firedog")

    async def test_increment_decrement(self):
        """Test .increment and .decrement methods."""
        await self.redis.set("entropic", 5)
        await self.redis.set("disentropic", 12.5)

        # Test default increment
        await self.redis.increment("entropic")
        self.assertEqual(await self.redis.get("entropic"), 6)

        # Test default decrement
        await self.redis.decrement("entropic")
        self.assertEqual(await self.redis.get("entropic"), 5)

        # Test float increment with float
        await self.redis.increment("disentropic", 2.0)
        self.assertEqual(await self.redis.get("disentropic"), 14.5)

        # Test float increment with int
        await self.redis.increment("disentropic", 2)
        self.assertEqual(await self.redis.get("disentropic"), 16.5)

        # Test negative increments, because why not.
        await self.redis.increment("entropic", -5)
        self.assertEqual(await self.redis.get("entropic"), 0)

        # Negative decrements? Sure.
        await self.redis.decrement("entropic", -5)
        self.assertEqual(await self.redis.get("entropic"), 5)

        # What about if we use a negative float to decrement an int?
        # This should convert the type into a float.
        await self.redis.decrement("entropic", -2.5)
        self.assertEqual(await self.redis.get("entropic"), 7.5)

        # Let's test that they raise the right errors
        with self.assertRaises(KeyError):
            await self.redis.increment("doesn't_exist!")

        await self.redis.set("stringthing", "stringthing")
        with self.assertRaises(TypeError):
            await self.redis.increment("stringthing")

    async def test_exceptions_raised(self):
        """Testing that the various RuntimeErrors are reachable."""
        class MyCog:
            cache = RedisCache()

            def __init__(self):
                self.other_cache = RedisCache()

        cog = MyCog()

        # Raises "No Bot instance"
        with self.assertRaises(RuntimeError):
            await cog.cache.get("john")

        # Raises "RedisCache has no namespace"
        with self.assertRaises(RuntimeError):
            await cog.other_cache.get("was")

        # Raises "You must access the RedisCache instance through the cog instance"
        with self.assertRaises(RuntimeError):
            await MyCog.cache.get("afraid")
