import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from discord import Colour, Embed

from bot.cogs import tags
from tests.helpers import MockBot, MockContext, MockTextChannel

CACHE = {
    "ytdl": {
        "title": "ytdl",
        "embed": {
            "description": "youtube,audio"
        }
    },
    "class": {
        "title": "class",
        "embed": {
            "description": "class"
        }
    },
    "classmethod": {
        "title": "classmethod",
        "embed": {
            "description": "classmethod"
        }
    },
    "return": {
        "title": "return",
        "embed": {
            "description": "return"
        }
    },
    "codeblock": {
        "title": "codeblock",
        "embed": {
            "description": "codeblock"
        }
    },
    "pep8": {
        "title": "pep8",
        "embed": {
            "description": "pep8"
        }
    },
    "off-topic": {
        "title": "off-topic",
        "embed": {
            "description": "off-topic"
        }
    }
}


class TagsBaseTests(unittest.TestCase):
    """Basic function tests in `Tags` cog that don't need very specific testing."""

    def setUp(self) -> None:
        self.bot = MockBot()
        self.cog = tags.Tags(self.bot)
        self.cog._cache = CACHE.copy()

    def test_get_tags(self):
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
    def test_fuzzy_search(self, regex):
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
                "expected_output": 33.33,
                "regex_split": iter(["fuu"])
            }
        ]

        for case in test_cases:
            with self.subTest(f"Should return {case['expected_output']} as match rate.", args=case["args"]):
                regex.sub.return_value = "foo"
                regex.split.return_value = case["regex_split"]

                actual = tags.Tags._fuzzy_search(*case["args"])

                self.assertAlmostEqual(actual, case["expected_output"], 2)
                regex.sub.called_once_with("", case["args"][0].lower())
                regex.split.called_once_with(case["args"][1].lower())

    def test_get_tag(self):
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

    def test_get_suggestions(self):
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
                "args": ("clas", None),
                "expected": [cache["classmethod"], cache["class"]]
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

                for expected_tag in case["expected"]:
                    self.assertTrue(any(expected_tag["title"] == actual_tag["title"] for actual_tag in actual))

    def test_get_tags_via_content(self):
        """Should return list of correct tags."""
        cache = self.cog._cache
        # Create tags names list for visual formatting
        tag_names_for_any_test = [
            "class",
            "classmethod"
        ]
        test_cases = [
            {
                "keywords": "youtube,audio",
                "check": all,
                "expected": [cache["ytdl"]]
            },
            {
                "keywords": "class",
                "check": any,
                "expected": [tag for tag_name, tag in cache.items() if tag_name in tag_names_for_any_test]
            }
        ]

        for case in test_cases:
            with self.subTest(keywords=case["keywords"], expected=case["expected"], check=case["check"]):
                actual = self.cog._get_tags_via_content(case["check"], case["keywords"])
                self.assertEqual(actual, case["expected"])


class TagsCommandsTests(unittest.IsolatedAsyncioTestCase):
    """`Tags` cog commands tests."""

    def setUp(self) -> None:
        self.bot = MockBot()
        self.ctx = MockContext(bot=self.bot)

    async def test_head_command(self):
        """Should invoke `!tags get` command from `!tag` command."""
        cog = tags.Tags(self.bot)

        self.assertIsNone(await cog.tags_group.callback(cog, self.ctx, tag_name="class"))
        self.ctx.invoke.assert_awaited_once_with(cog.get_command, tag_name="class")

    async def test_search_tags_with_keyword_command(self):
        """Should call `Tags._get_tags_via_content` and `Tags._send_matching_tags` with correct parameters."""
        cog = tags.Tags(self.bot)
        cog._get_tags_via_content = MagicMock(return_value="foo")
        cog._send_matching_tags = AsyncMock()

        self.assertIsNone(await cog.search_tag_content.callback(cog, self.ctx, keywords="youtube,audio"))
        cog._get_tags_via_content.assert_called_once_with(all, "youtube,audio")
        cog._send_matching_tags.assert_awaited_once_with(self.ctx, "youtube,audio", "foo")

    async def test_search_tags_any_command(self):
        """Should call `Tags._get_tags_via_content` and `Tags._send_matching_tags` with correct parameters."""
        test_cases = [
            {"keywords": "youtube,discord,foo"},
            {"keywords": "any"}
        ]

        for case in test_cases:
            with self.subTest(keywords=case["keywords"]):
                cog = tags.Tags(self.bot)
                cog._get_tags_via_content = MagicMock(return_value="foo")
                cog._send_matching_tags = AsyncMock()

                self.assertIsNone(
                    await cog.search_tag_content_any_keyword.callback(cog, self.ctx, keywords=case["keywords"])
                )
                cog._get_tags_via_content.assert_called_once_with(any, case["keywords"] or "any")
                cog._send_matching_tags.assert_awaited_once_with(self.ctx, case["keywords"], "foo")

    async def test_send_matching_tags(self):
        """Should return `None` and send correct embed."""
        cog = tags.Tags(self.bot)
        cog._cache = CACHE.copy()
        test_cases = [
            {
                "args": (self.ctx, "youtube,audio", [cog._cache["ytdl"]]),
                "expected": Embed.from_dict(cog._cache["ytdl"]["embed"])
            },
            {
                "args": (self.ctx, "foo", []),
                "expected": None
            },
            {
                "args": (self.ctx, "bar", [cog._cache["ytdl"], cog._cache["class"], cog._cache["classmethod"]]),
                "expected": Embed.from_dict({
                    "description": (
                        "\n**»**   class\n"
                        "**»**   classmethod\n"
                        "**»**   ytdl\n"
                    ),
                    "footer": {"text": tags.FOOTER_TEXT},
                    "title": "Here are the tags containing the given keyword:"
                })
            }
        ]

        for case in test_cases:
            with self.subTest(args=case["args"], expected=case["expected"]):
                self.ctx.send.reset_mock()

                self.assertIsNone(await cog._send_matching_tags(*case["args"]))
                if case["expected"] is None:
                    self.ctx.send.assert_not_awaited()
                else:
                    embed = self.ctx.send.call_args[1]["embed"]
                    self.ctx.send.assert_awaited_once_with(embed=embed)

                    self.assertEqual(embed.title, case["expected"].title)
                    self.assertEqual(embed.description, case["expected"].description)
                    self.assertEqual(embed.footer.text, case["expected"].footer.text)


class GetTagsCommandTests(unittest.IsolatedAsyncioTestCase):
    """Tests for `!tags get` command."""

    def setUp(self) -> None:
        self.bot = MockBot()
        self.ctx = MockContext(bot=self.bot, channel=MockTextChannel(id=1234))

    async def test_tag_on_cooldown(self):
        """Should not respond to chat due tag is under cooldown."""
        cog = tags.Tags(self.bot)
        cog.tag_cooldowns["ytdl"] = {"channel": 1234, "time": time.time()}

        self.assertIsNone(await cog.get_command.callback(cog, self.ctx, tag_name="ytdl"))
        self.ctx.send.assert_not_awaited()

    async def test_tags_list_empty(self):
        """Should send to chat (`ctx.send`) correct embed with information about no tags."""
        cog = tags.Tags(self.bot)
        cog._cache = {}

        self.assertIsNone(await cog.get_command.callback(cog, self.ctx, tag_name=None))
        embed = self.ctx.send.call_args[1]["embed"]
        self.ctx.send.assert_awaited_once_with(embed=embed)

        self.assertEqual(embed.description, "**There are no tags in the database!**")
        self.assertEqual(embed.colour, Colour.red())

    async def test_tags_list(self):
        """Should send to chat (`LinePaginator.paginate`) embed that contains all tags."""
        cog = tags.Tags(self.bot)
        cog._cache = CACHE.copy()

        self.assertIsNone(await cog.get_command.callback(cog, self.ctx, tag_name=None))
        embed = self.ctx.send.call_args[1]["embed"]

        self.assertEqual(embed.title, "**Current tags**")
        tags_string = "\n".join(sorted(f"**»**   {tag}" for tag in cog._cache))
        self.assertEqual(embed.description, f"\n{tags_string}\n")
        self.assertEqual(embed.footer.text, tags.FOOTER_TEXT)

    async def test_tag(self):
        """Should send correct embed to chat (`ctx.send`) with tag content."""
        cog = tags.Tags(self.bot)
        cog._cache = CACHE.copy()
        test_cases = [
            {"tag": tag["title"], "expected": tag["embed"]} for tag in cog._cache.values()
        ]
        test_cases.extend(
            [
                {
                    "tag": "clas",
                    "expected": {
                        "title": "Did you mean ...",
                        "description": "class\nclassmethod",
                        "type": "rich"
                    }
                },
                {
                    "tag": "clss",
                    "expected": None
                }
            ]
        )

        for case in test_cases:
            with self.subTest(tag_name=case["tag"], expected=case["expected"]):
                self.ctx.send.reset_mock()
                self.assertIsNone(await cog.get_command.callback(cog, self.ctx, tag_name=case["tag"]))
                if case["expected"] is None:
                    self.ctx.send.assert_not_awaited()
                else:
                    embed = self.ctx.send.call_args[1]["embed"]

                    self.assertEqual(embed.to_dict(), case["expected"])
                    self.ctx.send.assert_awaited_once_with(embed=embed)
