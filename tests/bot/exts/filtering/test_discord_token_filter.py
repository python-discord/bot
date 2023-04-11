import unittest
from re import Match
from unittest import mock
from unittest.mock import MagicMock, patch

import arrow

from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filters.unique import discord_token
from bot.exts.filtering._filters.unique.discord_token import DiscordTokenFilter, Token
from tests.helpers import MockBot, MockMember, MockMessage, MockTextChannel, autospec


class DiscordTokenFilterTests(unittest.IsolatedAsyncioTestCase):
    """Tests the DiscordTokenFilter class."""

    def setUp(self):
        """Adds the filter, a bot, and a message to the instance for usage in tests."""
        now = arrow.utcnow().timestamp()
        self.filter = DiscordTokenFilter({
            "id": 1,
            "content": "discord_token",
            "description": None,
            "settings": {},
            "additional_settings": {},
            "created_at": now,
            "updated_at": now
        })

        self.msg = MockMessage(id=555, content="hello world")
        self.msg.author.__str__ = MagicMock(return_value=self.msg.author.name)

        member = MockMember(id=123)
        channel = MockTextChannel(id=345)
        self.ctx = FilterContext(Event.MESSAGE, member, channel, "", self.msg)

    def test_extract_user_id_valid(self):
        """Should consider user IDs valid if they decode into an integer ID."""
        id_pairs = (
            ("NDcyMjY1OTQzMDYyNDEzMzMy", 472265943062413332),
            ("NDc1MDczNjI5Mzk5NTQ3OTA0", 475073629399547904),
            ("NDY3MjIzMjMwNjUwNzc3NjQx", 467223230650777641),
        )

        for token_id, user_id in id_pairs:
            with self.subTest(token_id=token_id):
                result = DiscordTokenFilter.extract_user_id(token_id)
                self.assertEqual(result, user_id)

    def test_extract_user_id_invalid(self):
        """Should consider non-digit and non-ASCII IDs invalid."""
        ids = (
            ("SGVsbG8gd29ybGQ", "non-digit ASCII"),
            ("0J_RgNC40LLQtdGCINC80LjRgA", "cyrillic text"),
            ("4pO14p6L4p6C4pG34p264pGl8J-EiOKSj-KCieKBsA", "Unicode digits"),
            ("4oaA4oaB4oWh4oWi4Lyz4Lyq4Lyr4LG9", "Unicode numerals"),
            ("8J2fjvCdn5nwnZ-k8J2fr_Cdn7rgravvvJngr6c", "Unicode decimals"),
            ("{hello}[world]&(bye!)", "ASCII invalid Base64"),
            ("Þíß-ï§-ňøẗ-våłìÐ", "Unicode invalid Base64"),
        )

        for user_id, msg in ids:
            with self.subTest(msg=msg):
                result = DiscordTokenFilter.extract_user_id(user_id)
                self.assertIsNone(result)

    def test_is_valid_timestamp_valid(self):
        """Should consider timestamps valid if they're greater than the Discord epoch."""
        timestamps = (
            "XsyRkw",
            "Xrim9Q",
            "XsyR-w",
            "XsySD_",
            "Dn9r_A",
        )

        for timestamp in timestamps:
            with self.subTest(timestamp=timestamp):
                result = DiscordTokenFilter.is_valid_timestamp(timestamp)
                self.assertTrue(result)

    def test_is_valid_timestamp_invalid(self):
        """Should consider timestamps invalid if they're before Discord epoch or can't be parsed."""
        timestamps = (
            ("B4Yffw", "DISCORD_EPOCH - TOKEN_EPOCH - 1"),
            ("ew", "123"),
            ("AoIKgA", "42076800"),
            ("{hello}[world]&(bye!)", "ASCII invalid Base64"),
            ("Þíß-ï§-ňøẗ-våłìÐ", "Unicode invalid Base64"),
        )

        for timestamp, msg in timestamps:
            with self.subTest(msg=msg):
                result = DiscordTokenFilter.is_valid_timestamp(timestamp)
                self.assertFalse(result)

    def test_is_valid_hmac_valid(self):
        """Should consider an HMAC valid if it has at least 3 unique characters."""
        valid_hmacs = (
            "VXmErH7j511turNpfURmb0rVNm8",
            "Ysnu2wacjaKs7qnoo46S8Dm2us8",
            "sJf6omBPORBPju3WJEIAcwW9Zds",
            "s45jqDV_Iisn-symw0yDRrk_jf4",
        )

        for hmac in valid_hmacs:
            with self.subTest(msg=hmac):
                result = DiscordTokenFilter.is_maybe_valid_hmac(hmac)
                self.assertTrue(result)

    def test_is_invalid_hmac_invalid(self):
        """Should consider an HMAC invalid if has fewer than 3 unique characters."""
        invalid_hmacs = (
            ("xxxxxxxxxxxxxxxxxx", "Single character"),
            ("XxXxXxXxXxXxXxXxXx", "Single character alternating case"),
            ("ASFasfASFasfASFASsf", "Three characters alternating-case"),
            ("asdasdasdasdasdasdasd", "Three characters one case"),
        )

        for hmac, msg in invalid_hmacs:
            with self.subTest(msg=msg):
                result = DiscordTokenFilter.is_maybe_valid_hmac(hmac)
                self.assertFalse(result)

    async def test_no_trigger_when_no_token(self):
        """False should be returned if the message doesn't contain a Discord token."""
        return_value = await self.filter.triggered_on(self.ctx)

        self.assertFalse(return_value)

    @autospec(DiscordTokenFilter, "extract_user_id", "is_valid_timestamp", "is_maybe_valid_hmac")
    @autospec("bot.exts.filtering._filters.unique.discord_token", "Token")
    @autospec("bot.exts.filtering._filters.unique.discord_token", "TOKEN_RE")
    def test_find_token_valid_match(
        self,
        token_re,
        token_cls,
        extract_user_id,
        is_valid_timestamp,
        is_maybe_valid_hmac,
    ):
        """The first match with a valid user ID, timestamp, and HMAC should be returned as a `Token`."""
        matches = [
            mock.create_autospec(Match, spec_set=True, instance=True),
            mock.create_autospec(Match, spec_set=True, instance=True),
        ]
        tokens = [
            mock.create_autospec(Token, spec_set=True, instance=True),
            mock.create_autospec(Token, spec_set=True, instance=True),
        ]

        token_re.finditer.return_value = matches
        token_cls.side_effect = tokens
        extract_user_id.side_effect = (None, True)  # The 1st match will be invalid, 2nd one valid.
        is_valid_timestamp.return_value = True
        is_maybe_valid_hmac.return_value = True

        return_value = DiscordTokenFilter.find_token_in_message(self.msg)

        self.assertEqual(tokens[1], return_value)

    @autospec(DiscordTokenFilter, "extract_user_id", "is_valid_timestamp", "is_maybe_valid_hmac")
    @autospec("bot.exts.filtering._filters.unique.discord_token", "Token")
    @autospec("bot.exts.filtering._filters.unique.discord_token", "TOKEN_RE")
    def test_find_token_invalid_matches(
        self,
        token_re,
        token_cls,
        extract_user_id,
        is_valid_timestamp,
        is_maybe_valid_hmac,
    ):
        """None should be returned if no matches have valid user IDs, HMACs, and timestamps."""
        token_re.finditer.return_value = [mock.create_autospec(Match, spec_set=True, instance=True)]
        token_cls.return_value = mock.create_autospec(Token, spec_set=True, instance=True)
        extract_user_id.return_value = None
        is_valid_timestamp.return_value = False
        is_maybe_valid_hmac.return_value = False

        return_value = DiscordTokenFilter.find_token_in_message(self.msg)

        self.assertIsNone(return_value)

    def test_regex_invalid_tokens(self):
        """Messages without anything looking like a token are not matched."""
        tokens = (
            "",
            "lemon wins",
            "..",
            "x.y",
            "x.y.",
            ".y.z",
            ".y.",
            "..z",
            "x..z",
            " . . ",
            "\n.\n.\n",
            "hellö.world.bye",
            "base64.nötbåse64.morebase64",
            "19jd3J.dfkm3d.€víł§tüff",
        )

        for token in tokens:
            with self.subTest(token=token):
                results = discord_token.TOKEN_RE.findall(token)
                self.assertEqual(len(results), 0)

    def test_regex_valid_tokens(self):
        """Messages that look like tokens should be matched."""
        # Don't worry, these tokens have been invalidated.
        tokens = (
            "NDcyMjY1OTQzMDYy_DEzMz-y.XsyRkw.VXmErH7j511turNpfURmb0rVNm8",
            "NDcyMjY1OTQzMDYyNDEzMzMy.Xrim9Q.Ysnu2wacjaKs7qnoo46S8Dm2us8",
            "NDc1MDczNjI5Mzk5NTQ3OTA0.XsyR-w.sJf6omBPORBPju3WJEIAcwW9Zds",
            "NDY3MjIzMjMwNjUwNzc3NjQx.XsySD_.s45jqDV_Iisn-symw0yDRrk_jf4",
        )

        for token in tokens:
            with self.subTest(token=token):
                results = discord_token.TOKEN_RE.fullmatch(token)
                self.assertIsNotNone(results, f"{token} was not matched by the regex")

    def test_regex_matches_multiple_valid(self):
        """Should support multiple matches in the middle of a string."""
        token_1 = "NDY3MjIzMjMwNjUwNzc3NjQx.XsyWGg.uFNEQPCc4ePwGh7egG8UicQssz8"  # noqa: S105
        token_2 = "NDcyMjY1OTQzMDYyNDEzMzMy.XsyWMw.l8XPnDqb0lp-EiQ2g_0xVFT1pyc"  # noqa: S105
        message = f"garbage {token_1} hello {token_2} world"

        results = discord_token.TOKEN_RE.finditer(message)
        results = [match[0] for match in results]
        self.assertCountEqual((token_1, token_2), results)

    @autospec("bot.exts.filtering._filters.unique.discord_token", "LOG_MESSAGE")
    def test_format_log_message(self, log_message):
        """Should correctly format the log message with info from the message and token."""
        token = Token("NDcyMjY1OTQzMDYyNDEzMzMy", "XsySD_", "s45jqDV_Iisn-symw0yDRrk_jf4")
        log_message.format.return_value = "Howdy"

        return_value = DiscordTokenFilter.format_log_message(self.msg.author, self.msg.channel, token)

        self.assertEqual(return_value, log_message.format.return_value)

    @patch("bot.instance", MockBot())
    @autospec("bot.exts.filtering._filters.unique.discord_token", "UNKNOWN_USER_LOG_MESSAGE")
    @autospec("bot.exts.filtering._filters.unique.discord_token", "get_or_fetch_member")
    async def test_format_userid_log_message_unknown(self, get_or_fetch_member, unknown_user_log_message):
        """Should correctly format the user ID portion when the actual user it belongs to is unknown."""
        token = Token("NDcyMjY1OTQzMDYyNDEzMzMy", "XsySD_", "s45jqDV_Iisn-symw0yDRrk_jf4")
        unknown_user_log_message.format.return_value = " Partner"
        get_or_fetch_member.return_value = None

        return_value = await DiscordTokenFilter.format_userid_log_message(token)

        self.assertEqual(return_value, (unknown_user_log_message.format.return_value, False))

    @patch("bot.instance", MockBot())
    @autospec("bot.exts.filtering._filters.unique.discord_token", "KNOWN_USER_LOG_MESSAGE")
    async def test_format_userid_log_message_bot(self, known_user_log_message):
        """Should correctly format the user ID portion when the ID belongs to a known bot."""
        token = Token("NDcyMjY1OTQzMDYyNDEzMzMy", "XsySD_", "s45jqDV_Iisn-symw0yDRrk_jf4")
        known_user_log_message.format.return_value = " Partner"

        return_value = await DiscordTokenFilter.format_userid_log_message(token)

        self.assertEqual(return_value, (known_user_log_message.format.return_value, True))

    @patch("bot.instance", MockBot())
    @autospec("bot.exts.filtering._filters.unique.discord_token", "KNOWN_USER_LOG_MESSAGE")
    async def test_format_log_message_user_token_user(self, user_token_message):
        """Should correctly format the user ID portion when the ID belongs to a known user."""
        token = Token("NDY3MjIzMjMwNjUwNzc3NjQx", "XsySD_", "s45jqDV_Iisn-symw0yDRrk_jf4")
        user_token_message.format.return_value = "Partner"

        return_value = await DiscordTokenFilter.format_userid_log_message(token)

        self.assertEqual(return_value, (user_token_message.format.return_value, True))
