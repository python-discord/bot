import unittest

import fakeredis
from redis import DataError

from bot.utils import RedisDict

redis_server = fakeredis.FakeServer()
RedisDict._redis = fakeredis.FakeStrictRedis(server=redis_server)


class RedisDictTests(unittest.TestCase):
    """Tests the RedisDict class from utils.redis_dict.py."""

    redis = RedisDict()

    def test_class_attribute_namespace(self):
        """Test that RedisDict creates a namespace automatically for class attributes."""
        self.assertEqual(self.redis._namespace, "RedisDictTests.redis")

    def test_custom_namespace(self):
        """Test that users can set a custom namespaces which never collide."""
        test_cases = (
            (RedisDict("firedog")._namespace, "firedog"),
            (RedisDict("firedog")._namespace, "firedog_"),
            (RedisDict("firedog")._namespace, "firedog__"),
        )

        for test_case, result in test_cases:
            self.assertEqual(test_case, result)

    def test_custom_namespace_takes_precedence(self):
        """Test that custom namespaces take precedence over class attribute ones."""
        class LemonJuice:
            citrus = RedisDict("citrus")
            watercat = RedisDict()

        test_class = LemonJuice()
        self.assertEqual(test_class.citrus._namespace, "citrus")
        self.assertEqual(test_class.watercat._namespace, "LemonJuice.watercat")

    def test_set_get_item(self):
        """Test that users can set and get items from the RedisDict."""
        self.redis['favorite_fruit'] = 'melon'
        self.redis['favorite_number'] = 86
        self.assertEqual(self.redis['favorite_fruit'], 'melon')
        self.assertEqual(self.redis['favorite_number'], 86)

    def test_set_item_value_types(self):
        """Test that setitem rejects values that are not JSON serializable."""
        with self.assertRaises(TypeError):
            self.redis['favorite_thing'] = object
            self.redis['favorite_stuff'] = RedisDict

    def test_set_item_key_types(self):
        """Test that setitem rejects keys that are not strings, ints or floats."""
        fruits = ["lemon", "melon", "apple"]

        with self.assertRaises(DataError):
            self.redis[fruits] = "nice"

    def test_get_method(self):
        """Test that the .get method works like in a dict."""
        self.redis['favorite_movie'] = 'Code Jam Highlights'

        self.assertEqual(self.redis.get('favorite_movie'), 'Code Jam Highlights')
        self.assertEqual(self.redis.get('favorite_youtuber', 'pydis'), 'pydis')
        self.assertIsNone(self.redis.get('favorite_dog'))

    def test_membership(self):
        """Test that we can reliably use the `in` operator with our RedisDict."""
        self.redis['favorite_country'] = "Burkina Faso"

        self.assertIn('favorite_country', self.redis)
        self.assertNotIn('favorite_dentist', self.redis)

    def test_del_item(self):
        """Test that users can delete items from the RedisDict."""
        self.redis['favorite_band'] = "Radiohead"
        self.assertIn('favorite_band', self.redis)

        del self.redis['favorite_band']
        self.assertNotIn('favorite_band', self.redis)

    def test_iter(self):
        """Test that the RedisDict can be iterated."""
        self.redis.clear()
        test_cases = (
            ('favorite_turtle', 'Donatello'),
            ('second_favorite_turtle', 'Leonardo'),
            ('third_favorite_turtle', 'Raphael'),
        )
        for key, value in test_cases:
            self.redis[key] = value

        # Test regular iteration
        for test_case, key in zip(test_cases, self.redis):
            value = test_case[1]
            self.assertEqual(self.redis[key], value)

        # Test .items iteration
        for key, value in self.redis.items():
            self.assertEqual(self.redis[key], value)

        # Test .keys iteration
        for test_case, key in zip(test_cases, self.redis.keys()):
            value = test_case[1]
            self.assertEqual(self.redis[key], value)

    def test_len(self):
        """Test that we can get the correct len() from the RedisDict."""
        self.redis.clear()
        self.redis['one'] = 1
        self.redis['two'] = 2
        self.redis['three'] = 3
        self.assertEqual(len(self.redis), 3)

        self.redis['four'] = 4
        self.assertEqual(len(self.redis), 4)

    def test_copy(self):
        """Test that the .copy method returns a workable dictionary copy."""
        copy = self.redis.copy()
        local_copy = dict(self.redis.items())
        self.assertIs(type(copy), dict)
        self.assertEqual(copy, local_copy)

    def test_clear(self):
        """Test that the .clear method removes the entire hash."""
        self.redis.clear()
        self.redis['teddy'] = "with me"
        self.redis['in my dreams'] = "you have a weird hat"
        self.assertEqual(len(self.redis), 2)

        self.redis.clear()
        self.assertEqual(len(self.redis), 0)

    def test_pop(self):
        """Test that we can .pop an item from the RedisDict."""
        self.redis.clear()
        self.redis['john'] = 'was afraid'

        self.assertEqual(self.redis.pop('john'), 'was afraid')
        self.assertEqual(self.redis.pop('pete', 'breakneck'), 'breakneck')
        self.assertEqual(len(self.redis), 0)

    def test_popitem(self):
        """Test that we can .popitem an item from the RedisDict."""
        self.redis.clear()
        self.redis['john'] = 'the revalator'
        self.redis['teddy'] = 'big bear'

        self.assertEqual(len(self.redis), 2)
        self.assertEqual(self.redis.popitem(), 'big bear')
        self.assertEqual(len(self.redis), 1)

    def test_setdefault(self):
        """Test that we can .setdefault an item from the RedisDict."""
        self.redis.clear()
        self.redis.setdefault('john', 'is yellow and weak')
        self.assertEqual(self.redis['john'], 'is yellow and weak')

        with self.assertRaises(TypeError):
            self.redis.setdefault('geisha', object)

    def test_update(self):
        """Test that we can .update the RedisDict with multiple items."""
        self.redis.clear()
        self.redis["reckfried"] = "lona"
        self.redis["bel air"] = "prince"
        self.redis.update({
            "reckfried": "jona",
            "mega": "hungry, though",
        })

        result = {
            "reckfried": "jona",
            "bel air": "prince",
            "mega": "hungry, though",
        }
        self.assertEqual(self.redis.copy(), result)

    def test_equals(self):
        """Test that RedisDicts can be compared with == and !=."""
        new_redis_dict = RedisDict("firedog_the_sequel")
        new_new_redis_dict = new_redis_dict

        self.assertEqual(new_redis_dict, new_new_redis_dict)
        self.assertNotEqual(new_redis_dict, self.redis)
