import unittest
from pathlib import Path

from bot.cogs import tags
from tests.helpers import MockBot


class TagsBaseTests(unittest.IsolatedAsyncioTestCase):
    """Basic function tests in `Tags` cog that don't need very specific testing."""

    def setUp(self) -> None:
        self.bot = MockBot()
        self.cog = tags.Tags(self.bot)

    async def test_get_tags(self):
        """Should return `Dict` of tags, fetched from resources and have correct keys."""
        actual = tags.Tags.get_tags()

        tags_files = Path("bot", "resources", "tags").iterdir()

        self.assertEqual(len(actual), sum(1 for _ in tags_files))
        for k, v in actual.items():
            with self.subTest("Should have following keys: `title`, `embed`, `description`", tag=k, values=v):
                self.assertTrue("title" in v)
                self.assertTrue("embed" in v)
                self.assertTrue("description" in v["embed"])
