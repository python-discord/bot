import unittest

from bot import utils


class CaseInsensitiveDictTests(unittest.TestCase):
    """Tests for the `CaseInsensitiveDict` container."""

    def test_case_insensitive_key_access(self):
        """Tests case insensitive key access and storage."""
        instance = utils.CaseInsensitiveDict()

        key = 'LEMON'
        value = 'trees'

        instance[key] = value
        self.assertIn(key, instance)
        self.assertEqual(instance.get(key), value)
        self.assertEqual(instance.get(key.casefold()), value)
        self.assertEqual(instance.pop(key.casefold()), value)
        self.assertNotIn(key, instance)
        self.assertNotIn(key.casefold(), instance)

        instance.setdefault(key, value)
        del instance[key]
        self.assertNotIn(key, instance)

    def test_initialization_from_kwargs(self):
        """Tests creating the dictionary from keyword arguments."""
        instance = utils.CaseInsensitiveDict({'FOO': 'bar'})
        self.assertEqual(instance['foo'], 'bar')

    def test_update_from_other_mapping(self):
        """Tests updating the dictionary from another mapping."""
        instance = utils.CaseInsensitiveDict()
        instance.update({'FOO': 'bar'})
        self.assertEqual(instance['foo'], 'bar')
