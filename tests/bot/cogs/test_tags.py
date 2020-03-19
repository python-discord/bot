import unittest
from pathlib import Path
from unittest.mock import patch

from bot.cogs import tags
from tests.helpers import MockBot, MockContext


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
            with self.subTest("Should have following keys: `title`, `embed` (under it `description`)", tag=k, values=v):
                self.assertTrue("title" in v)
                self.assertTrue("embed" in v)
                self.assertTrue("description" in v["embed"])

    @patch("bot.cogs.tags.REGEX_NON_ALPHABET")
    async def test_fuzzy_search(self, regex):
        """Should return correct words match rate."""
        test_cases = [
            {
                "args": ("foo", "foo"),
                "expected_output": 100.0,
                "regex_split": iter(["foo"])
            },
            {
                "args": ("foo", "bar"),
                "expected_output": 0.0,
                "regex_split": iter(["bar"])
            },
            {
                "args": ("foo", "fuu"),
                "expected_output": 33.33333333333333,
                "regex_split": iter(["fuu"])
            }
        ]

        for case in test_cases:
            with self.subTest(f"Should return {case['expected_output']} as match rate.", args=case["args"]):
                regex.sub.return_value = "foo"
                regex.split.return_value = case["regex_split"]

                actual = tags.Tags._fuzzy_search(*case["args"])

                self.assertEqual(actual, case["expected_output"])
                regex.sub.called_once_with("", case["args"][0].lower())
                regex.split.called_once_with(case["args"][1].lower())

    async def test_get_tag(self):
        """Should return correct tag from Cog cache."""
        cache = self.cog._cache
        test_cases = [
            {"name": tag_name, "expected": tag} for tag_name, tag in cache.items()
        ]
        test_cases.append(
            {
                "name": "retur",
                "expected": cache["return"]
            }
        )
        for case in test_cases:
            with self.subTest(tag_name=case["name"], expected=case["expected"]):
                actual = self.cog._get_tag(case["name"])
                self.assertEqual(actual[0], case["expected"])

    async def test_get_suggestions(self):
        """Should return correct list of tags and interact with `_fuzzy_search`."""
        cache = self.cog._cache
        test_cases = [
            {
                "args": ("codeblck", None),
                "expected": [cache["codeblock"]]
            },
            {
                "args": ("pep", None),
                "expected": [cache["pep8"]]
            },
            {
                "args": ("class", None),
                "expected": [cache["class"], cache["classmethod"]]
            },
            {
                "args": ("o-topc", [100, 90, 80, 70, 60, 50, 40, 30, 20, 10]),
                "expected": [cache["off-topic"]]
            },
            {
                "args": ("my-test-string", None),
                "expected": []
            }
        ]
        for case in test_cases:
            with self.subTest(args=case["args"], expected=case["expected"]):
                actual = self.cog._get_suggestions(*case["args"])

                self.assertEqual(actual, case["expected"])


class TagsCommandsTests(unittest.IsolatedAsyncioTestCase):
    """`Tags` cog commands tests."""

    def setUp(self) -> None:
        self.bot = MockBot()
        self.cog = tags.Tags(self.bot)
        self.ctx = MockContext(bot=self.bot)

    async def test_head_command(self):
        """Should invoke `!tags get` command from `!tag` command."""
        self.assertIsNone(await self.cog.tags_group.callback(self.cog, self.ctx, tag_name="class"))
        self.ctx.invoke.assert_awaited_once_with(self.cog.get_command, tag_name="class")
