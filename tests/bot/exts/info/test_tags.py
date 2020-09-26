import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

from discord import Colour, Embed

from bot.exts.info import tags
from tests.helpers import MockBot, MockContext, MockMember, MockRole, MockTextChannel


class TagsBaseTests(unittest.TestCase):
    """Basic function tests in `Tags` cog that don't need very specific testing."""

    def setUp(self) -> None:
        self.bot = MockBot()
        with patch("bot.exts.info.tags.Path") as path:
            path.return_value = Path("tests", "bot", "resources", "testing-tags")
            self.cog = tags.Tags(self.bot)
        self.member = MockMember(roles=(MockRole(name="Developers"),))

    def test_get_tags(self):
        """Should return `Dict` of tags, fetched from resources and have correct keys."""
        testing_path = Path("tests", "bot", "resources", "testing-tags")
        with patch("bot.exts.info.tags.Path") as path:
            path.return_value = testing_path
            actual = tags.Tags.get_tags()

        self.assertEqual(len(actual), len(list(testing_path.iterdir())))
        for file in testing_path.glob("**/*"):
            if file.is_file():
                name = file.name.replace(".md", "")
                self.assertIn(name, actual)
                self.assertEqual(file.read_text(encoding="utf-8"), actual[name]["embed"]["description"])
                parents = list(file.relative_to(testing_path).parents)
                if len(parents) > 1:
                    self.assertEqual(parents[-2].name, actual[name]["restricted_to"])

    @patch("bot.exts.info.tags.REGEX_NON_ALPHABET")
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
        """Should return list of correct tags and call access check."""
        cache = self.cog._cache
        self.cog.check_accessibility = MagicMock()
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
            },
            {
                "keywords": "youtube,audio,",
                "check": all,
                "expected": [cache["ytdl"]]
            },
            {
                "keywords": ",",
                "check": all,
                "expected": [cache["pep8"], cache["ytdl"]]
            }
        ]

        for case in test_cases:
            with self.subTest(keywords=case["keywords"], expected=case["expected"], check=case["check"]):
                self.cog.check_accessibility.reset_mock()
                actual = self.cog._get_tags_via_content(case["check"], case["keywords"], self.member)
                self.assertEqual(actual, case["expected"])
                self.cog.check_accessibility.assert_called()

    def test_check_accessibility(self):
        """Should return does user have access to tag."""
        test_cases = [
            {
                "member": MockMember(roles=(MockRole(name="Developers"),)),
                "restricted_to": "moderators",
                "expected": False
            },
            {
                "member": MockMember(roles=(MockRole(name="Developers"), MockRole(name="Moderators"))),
                "restricted_to": "moderators",
                "expected": True
            }
        ]

        for case in test_cases:
            with self.subTest(restricted_to=case["restricted_to"], expected=case["expected"]):
                actual = self.cog.check_accessibility(case["member"], {"restricted_to": case["restricted_to"]})
                self.assertEqual(actual, case["expected"])


class TagsCommandsTests(unittest.IsolatedAsyncioTestCase):
    """`Tags` cog commands tests."""

    def setUp(self) -> None:
        self.bot = MockBot()
        self.member = MockMember(roles=(MockRole(name="Developers"),))
        self.ctx = MockContext(bot=self.bot, author=self.member)
        with patch("bot.exts.info.tags.Path") as path:
            path.return_value = Path("tests", "bot", "resources", "testing-tags")
            self.cog = tags.Tags(self.bot)

    async def test_head_command(self):
        """Should invoke `!tags get` command from `!tag` command."""
        self.assertIsNone(await self.cog.tags_group.callback(self.cog, self.ctx, tag_name="class"))
        self.ctx.invoke.assert_awaited_once_with(self.cog.get_command, tag_name="class")

    async def test_search_tags_with_keyword_command(self):
        """Should call `Tags._get_tags_via_content` and `Tags._send_matching_tags` with correct parameters."""
        self.cog._get_tags_via_content = MagicMock(return_value="foo")
        self.cog._send_matching_tags = AsyncMock()

        self.assertIsNone(await self.cog.search_tag_content.callback(self.cog, self.ctx, keywords="youtube,audio"))
        self.cog._get_tags_via_content.assert_called_once_with(all, "youtube,audio", self.member)
        self.cog._send_matching_tags.assert_awaited_once_with(self.ctx, "youtube,audio", "foo")

    async def test_search_tags_any_command(self):
        """Should call `Tags._get_tags_via_content` and `Tags._send_matching_tags` with correct parameters."""
        test_cases = [
            {"keywords": "youtube,discord,foo"},
            {"keywords": "any"}
        ]
        self.cog._get_tags_via_content = MagicMock(return_value="foo")
        self.cog._send_matching_tags = AsyncMock()

        for case in test_cases:
            with self.subTest(keywords=case["keywords"]):
                self.cog._get_tags_via_content.reset_mock()
                self.cog._send_matching_tags.reset_mock()

                self.assertIsNone(
                    await self.cog.search_tag_content_any_keyword.callback(
                        self.cog, self.ctx, keywords=case["keywords"]
                    )
                )
                self.cog._get_tags_via_content.assert_called_once_with(any, case["keywords"] or "any", self.member)
                self.cog._send_matching_tags.assert_awaited_once_with(self.ctx, case["keywords"], "foo")

    async def test_send_matching_tags(self):
        """Should return `None` and send correct embed."""
        cache = self.cog._cache
        test_cases = [
            {
                "args": (self.ctx, "youtube,audio", [cache["ytdl"]]),
                "expected": Embed.from_dict(cache["ytdl"]["embed"])
            },
            {
                "args": (self.ctx, "foo", []),
                "expected": None
            },
            {
                "args": (self.ctx, "bar", [cache["ytdl"], cache["class"], cache["classmethod"]]),
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

                self.assertIsNone(await self.cog._send_matching_tags(*case["args"]))
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
        self.member = MockMember(roles=(MockRole(name="Developers"), MockRole(name="Moderators")))
        self.ctx = MockContext(bot=self.bot, channel=MockTextChannel(id=1234), author=self.member)
        with patch("bot.exts.info.tags.Path") as path:
            path.return_value = Path("tests", "bot", "resources", "testing-tags")
            self.cog = tags.Tags(self.bot)

    async def test_tag_on_cooldown(self):
        """Should not respond to chat due tag is under cooldown."""
        self.cog.tag_cooldowns["ytdl"] = {"channel": 1234, "time": time.time()}

        self.assertIsNone(await self.cog.get_command.callback(self.cog, self.ctx, tag_name="ytdl"))
        self.ctx.send.assert_not_awaited()

    async def test_tags_list_empty(self):
        """Should send to chat (`ctx.send`) correct embed with information about no tags."""
        self.cog._cache = {}
        self.assertIsNone(await self.cog.get_command.callback(self.cog, self.ctx, tag_name=None))
        embed = self.ctx.send.call_args[1]["embed"]
        self.ctx.send.assert_awaited_once_with(embed=embed)

        self.assertEqual(embed.description, "**There are no tags in the database!**")
        self.assertEqual(embed.colour, Colour.red())

    async def test_tags_list(self):
        """Should send to chat (`LinePaginator.paginate`) embed that contains all tags."""
        self.assertIsNone(await self.cog.get_command.callback(self.cog, self.ctx, tag_name=None))
        embed = self.ctx.send.call_args[1]["embed"]

        self.assertEqual(embed.title, "**Current tags**")
        tags_string = "\n".join(sorted(f"**»**   {tag}" for tag in self.cog._cache))
        self.assertEqual(embed.description, f"\n{tags_string}\n")
        self.assertEqual(embed.footer.text, tags.FOOTER_TEXT)

    async def test_tags_list_permissions(self):
        """Should not include tag to list when user don't have permissions to use that tag."""
        self.ctx.author = MockMember(roles=(MockRole(name="Developers"),))
        self.assertIsNone(await self.cog.get_command.callback(self.cog, self.ctx, tag_name=None))
        embed = self.ctx.send.call_args[1]["embed"]
        tags_string = "\n".join(
            sorted(f"**»**   {tag}" for tag in self.cog._cache if self.cog._cache[tag]["restricted_to"] != "moderators")
        )
        self.assertEqual(embed.description, f"\n{tags_string}\n")

    async def test_tag(self):
        """Should send correct embed to chat (`ctx.send`) with tag content."""
        test_cases = [
            {"tag": tag["title"], "expected": tag["embed"]} for tag in self.cog._cache.values()
        ]
        test_cases.extend(
            [
                {
                    "tag": "clas",
                    "expected": {
                        "title": "Did you mean ...",
                        "description": "classmethod\nclass",
                        "type": "rich"
                    }
                },
                {
                    "tag": "clss",
                    "expected": None
                }
            ]
        )
        self.cog.bot.stats.incr = MagicMock()

        for case in test_cases:
            with self.subTest(tag_name=case["tag"], expected=case["expected"]):
                self.ctx.send.reset_mock()
                self.cog.bot.stats.incr.reset_mock()
                self.assertIsNone(await self.cog.get_command.callback(self.cog, self.ctx, tag_name=case["tag"]))
                if case["expected"] is None:
                    self.ctx.send.assert_not_awaited()
                else:
                    embed = self.ctx.send.call_args[1]["embed"]

                    self.assertEqual(embed.to_dict(), case["expected"])
                    self.ctx.send.assert_awaited_once_with(embed=embed)

    @patch("bot.exts.info.tags.time.time", MagicMock(return_value=1234))
    async def test_tag_cooldown(self):
        """Should set tag to cooldown when not in test channels."""
        self.assertIsNone(await self.cog.get_command.callback(self.cog, self.ctx, tag_name="class"))
        self.assertIn("class", self.cog.tag_cooldowns)
        self.assertEqual(self.cog.tag_cooldowns["class"], {"time": 1234, "channel": self.ctx.channel.id})

    async def test_tag_cooldown_test_channel(self):
        """Should not set tag to cooldown when in test channels."""
        with patch("bot.exts.info.tags.TEST_CHANNELS", (1234,)):
            self.assertIsNone(await self.cog.get_command.callback(self.cog, self.ctx, tag_name="class"))
        self.assertNotIn("class", self.cog.tag_cooldowns)

    @patch("bot.exts.info.tags.Tags.check_accessibility")
    async def test_tag_permission_check(self, check_accessibility_mock):
        """Should call check_accessibility for every tag that _get_tag returns."""
        self.assertIsNone(await self.cog.get_command.callback(self.cog, self.ctx, tag_name="clas"))
        calls = []
        for tag in self.cog._get_tag("clas"):
            calls.append(call(self.ctx.author, tag))
            calls.append(call().__bool__())
        check_accessibility_mock.assert_has_calls(calls)

    async def test_tag_using_permissions(self):
        """Should silently return when user don't have required role to use tag."""
        test_cases = [
            {
                "member": MockMember(roles=(MockRole(name="Developers"), MockRole(name="Moderators"))),
                "tag": "test-mod-tag",
                "should_access": True
            },
            {
                "member": MockMember(roles=(MockRole(name="Developers"),)),
                "tag": "test-mod-tag",
                "should_access": False
            }
        ]

        for case in test_cases:
            with self.subTest(tag=case["tag"], should_access=case["should_access"]):
                self.ctx.reset_mock()
                await self.cog.get_command.callback(self.cog, self.ctx, tag_name=case["tag"])
                if case["should_access"]:
                    self.ctx.send.assert_awaited_once()
                else:
                    self.ctx.send.assert_not_awaited()


class TagsSetupTests(unittest.TestCase):
    """Tests for tags cog `setup` function."""

    def test_setup(self):
        """Should call `bot.add_cog`."""
        bot = MockBot()
        tags.setup(bot)
        bot.add_cog.assert_called_once()
