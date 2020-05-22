import unittest

import fakeredis.aioredis

from bot.utils import RedisCache
from tests import helpers


class RedisCacheTests(unittest.IsolatedAsyncioTestCase):
    """Tests the RedisDict class from utils.redis_dict.py."""

    redis = RedisCache()

    async def asyncSetUp(self):  # noqa: N802 - this special method can't be all lowercase
        """Sets up the objects that only have to be initialized once."""
        self.bot = helpers.MockBot()
        self.bot.redis_session = await fakeredis.aioredis.create_redis_pool()

    def test_class_attribute_namespace(self):
        """Test that RedisDict creates a namespace automatically for class attributes."""
        self.assertEqual(self.redis._namespace, "RedisCacheTests.redis")
        # Test that errors are raised when this isn't true.

    # def test_set_get_item(self):
    #     """Test that users can set and get items from the RedisDict."""
    #     self.redis['favorite_fruit'] = 'melon'
    #     self.redis['favorite_number'] = 86
    #     self.assertEqual(self.redis['favorite_fruit'], 'melon')
    #     self.assertEqual(self.redis['favorite_number'], 86)
    #
    # def test_set_item_types(self):
    #     """Test that setitem rejects keys and values that are not strings, ints or floats."""
    #     fruits = ["lemon", "melon", "apple"]
    #
    #     with self.assertRaises(DataError):
    #         self.redis[fruits] = "nice"
    #
    # def test_contains(self):
    #     """Test that we can reliably use the `in` operator with our RedisDict."""
    #     self.redis['favorite_country'] = "Burkina Faso"
    #
    #     self.assertIn('favorite_country', self.redis)
    #     self.assertNotIn('favorite_dentist', self.redis)
    #
    # def test_items(self):
    #     """Test that the RedisDict can be iterated."""
    #     self.redis.clear()
    #     test_cases = (
    #         ('favorite_turtle', 'Donatello'),
    #         ('second_favorite_turtle', 'Leonardo'),
    #         ('third_favorite_turtle', 'Raphael'),
    #     )
    #     for key, value in test_cases:
    #         self.redis[key] = value
    #
    #     # Test regular iteration
    #     for test_case, key in zip(test_cases, self.redis):
    #         value = test_case[1]
    #         self.assertEqual(self.redis[key], value)
    #
    #     # Test .items iteration
    #     for key, value in self.redis.items():
    #         self.assertEqual(self.redis[key], value)
    #
    #     # Test .keys iteration
    #     for test_case, key in zip(test_cases, self.redis.keys()):
    #         value = test_case[1]
    #         self.assertEqual(self.redis[key], value)
    #
    # def test_length(self):
    #     """Test that we can get the correct len() from the RedisDict."""
    #     self.redis.clear()
    #     self.redis['one'] = 1
    #     self.redis['two'] = 2
    #     self.redis['three'] = 3
    #     self.assertEqual(len(self.redis), 3)
    #
    #     self.redis['four'] = 4
    #     self.assertEqual(len(self.redis), 4)
    #
    # def test_to_dict(self):
    #     """Test that the .copy method returns a workable dictionary copy."""
    #     copy = self.redis.copy()
    #     local_copy = dict(self.redis.items())
    #     self.assertIs(type(copy), dict)
    #     self.assertEqual(copy, local_copy)
    #
    # def test_clear(self):
    #     """Test that the .clear method removes the entire hash."""
    #     self.redis.clear()
    #     self.redis['teddy'] = "with me"
    #     self.redis['in my dreams'] = "you have a weird hat"
    #     self.assertEqual(len(self.redis), 2)
    #
    #     self.redis.clear()
    #     self.assertEqual(len(self.redis), 0)
    #
    # def test_pop(self):
    #     """Test that we can .pop an item from the RedisDict."""
    #     self.redis.clear()
    #     self.redis['john'] = 'was afraid'
    #
    #     self.assertEqual(self.redis.pop('john'), 'was afraid')
    #     self.assertEqual(self.redis.pop('pete', 'breakneck'), 'breakneck')
    #     self.assertEqual(len(self.redis), 0)
    #
    # def test_update(self):
    #     """Test that we can .update the RedisDict with multiple items."""
    #     self.redis.clear()
    #     self.redis["reckfried"] = "lona"
    #     self.redis["bel air"] = "prince"
    #     self.redis.update({
    #         "reckfried": "jona",
    #         "mega": "hungry, though",
    #     })
    #
    #     result = {
    #         "reckfried": "jona",
    #         "bel air": "prince",
    #         "mega": "hungry, though",
    #     }
    #     self.assertEqual(self.redis.copy(), result)
