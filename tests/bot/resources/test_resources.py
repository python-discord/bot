import json
import unittest
from pathlib import Path


class ResourceValidationTests(unittest.TestCase):
    """Validates resources used by the bot."""
    def test_stars_valid(self):
        """The resource `bot/resources/stars.json` should contain a list of strings."""
        path = Path("bot", "resources", "stars.json")
        content = path.read_text()
        data = json.loads(content)

        self.assertIsInstance(data, list)
        for name in data:
            with self.subTest(name=name):
                self.assertIsInstance(name, str)
