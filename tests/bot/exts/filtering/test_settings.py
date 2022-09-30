import unittest

import bot.exts.filtering._settings
from bot.exts.filtering._settings import create_settings


class FilterTests(unittest.TestCase):
    """Test functionality of the Settings class and its subclasses."""

    def test_create_settings_returns_none_for_empty_data(self):
        """`create_settings` should return a tuple of two Nones when passed an empty dict."""
        result = create_settings({})

        self.assertEqual(result, (None, None))

    def test_unrecognized_entry_makes_a_warning(self):
        """When an unrecognized entry name is passed to `create_settings`, it should be added to `_already_warned`."""
        create_settings({"abcd": {}})

        self.assertIn("abcd", bot.exts.filtering._settings._already_warned)
