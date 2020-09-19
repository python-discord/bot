import unittest
from re import Match
from unittest import mock
from unittest.mock import MagicMock

from discord import Colour, NotFound

from bot import constants
from bot.cogs import token_remover
from bot.cogs.moderation import ModLog
from bot.cogs.token_remover import Token, TokenRemover
from tests.helpers import MockBot, MockMessage, autospec


class TokenRemoverTests(unittest.IsolatedAsyncioTestCase):
    """Tests the `TokenRemover` cog."""

    def setUp(self):
        """Adds the cog, a bot, and a message to the instance for usage in tests."""
        self.bot = MockBot()
        self.cog = TokenRemover(bot=self.bot)

        self.msg = MockMessage(id=555, content="hello world")
        self.msg.channel.mention = "#lemonade-stand"
        self.msg.guild.get_member = MagicMock(return_value="Bob")
        self.msg.author.__str__ = MagicMock(return_value=self.msg.author.name)
        self.msg.author.avatar_url_as.return_value = "picture-lemon.png"

    def test_is_valid_user_id_valid(self):
        """Should consider user IDs valid if they decode entirely to ASCII digits."""
        ids = (
            "NDcyMjY1OTQzMDYyNDEzMzMy",
            "NDc1MDczNjI5Mzk5NTQ3OTA0",
            "NDY3MjIzMjMwNjUwNzc3NjQx",
        )

        for user_id in ids:
            with self.subTest(user_id=user_id):
                result = TokenRemover.is_valid_user_id(user_id)
                self.assertTrue(result)

    def test_is_valid_user_id_invalid(self):
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
                result = TokenRemover.is_valid_user_id(user_id)
                self.assertFalse(result)

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
                result = TokenRemover.is_valid_timestamp(timestamp)
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
                result = TokenRemover.is_valid_timestamp(timestamp)
                self.assertFalse(result)

    def test_mod_log_property(self):
        """The `mod_log` property should ask the bot to return the `ModLog` cog."""
        self.bot.get_cog.return_value = 'lemon'
        self.assertEqual(self.cog.mod_log, self.bot.get_cog.return_value)
        self.bot.get_cog.assert_called_once_with('ModLog')

    async def test_on_message_edit_uses_on_message(self):
        """The edit listener should delegate handling of the message to the normal listener."""
        self.cog.on_message = mock.create_autospec(self.cog.on_message, spec_set=True)

        await self.cog.on_message_edit(MockMessage(), self.msg)
        self.cog.on_message.assert_awaited_once_with(self.msg)

    @autospec(TokenRemover, "find_token_in_message", "take_action")
    async def test_on_message_takes_action(self, find_token_in_message, take_action):
        """Should take action if a valid token is found when a message is sent."""
        cog = TokenRemover(self.bot)
        found_token = "foobar"
        find_token_in_message.return_value = found_token

        await cog.on_message(self.msg)

        find_token_in_message.assert_called_once_with(self.msg)
        take_action.assert_awaited_once_with(cog, self.msg, found_token)

    @autospec(TokenRemover, "find_token_in_message", "take_action")
    async def test_on_message_skips_missing_token(self, find_token_in_message, take_action):
        """Shouldn't take action if a valid token isn't found when a message is sent."""
        cog = TokenRemover(self.bot)
        find_token_in_message.return_value = False

        await cog.on_message(self.msg)

        find_token_in_message.assert_called_once_with(self.msg)
        take_action.assert_not_awaited()

    @autospec(TokenRemover, "find_token_in_message")
    async def test_on_message_ignores_dms_bots(self, find_token_in_message):
        """Shouldn't parse a message if it is a DM or authored by a bot."""
        cog = TokenRemover(self.bot)
        dm_msg = MockMessage(guild=None)
        bot_msg = MockMessage(author=MagicMock(bot=True))

        for msg in (dm_msg, bot_msg):
            await cog.on_message(msg)
            find_token_in_message.assert_not_called()

    @autospec("bot.cogs.token_remover", "TOKEN_RE")
    def test_find_token_no_matches(self, token_re):
        """None should be returned if the regex matches no tokens in a message."""
        token_re.finditer.return_value = ()

        return_value = TokenRemover.find_token_in_message(self.msg)

        self.assertIsNone(return_value)
        token_re.finditer.assert_called_once_with(self.msg.content)

    @autospec(TokenRemover, "is_valid_user_id", "is_valid_timestamp")
    @autospec("bot.cogs.token_remover", "Token")
    @autospec("bot.cogs.token_remover", "TOKEN_RE")
    def test_find_token_valid_match(self, token_re, token_cls, is_valid_id, is_valid_timestamp):
        """The first match with a valid user ID and timestamp should be returned as a `Token`."""
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
        is_valid_id.side_effect = (False, True)  # The 1st match will be invalid, 2nd one valid.
        is_valid_timestamp.return_value = True

        return_value = TokenRemover.find_token_in_message(self.msg)

        self.assertEqual(tokens[1], return_value)
        token_re.finditer.assert_called_once_with(self.msg.content)

    @autospec(TokenRemover, "is_valid_user_id", "is_valid_timestamp")
    @autospec("bot.cogs.token_remover", "Token")
    @autospec("bot.cogs.token_remover", "TOKEN_RE")
    def test_find_token_invalid_matches(self, token_re, token_cls, is_valid_id, is_valid_timestamp):
        """None should be returned if no matches have valid user IDs or timestamps."""
        token_re.finditer.return_value = [mock.create_autospec(Match, spec_set=True, instance=True)]
        token_cls.return_value = mock.create_autospec(Token, spec_set=True, instance=True)
        is_valid_id.return_value = False
        is_valid_timestamp.return_value = False

        return_value = TokenRemover.find_token_in_message(self.msg)

        self.assertIsNone(return_value)
        token_re.finditer.assert_called_once_with(self.msg.content)

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
                results = token_remover.TOKEN_RE.findall(token)
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
                results = token_remover.TOKEN_RE.fullmatch(token)
                self.assertIsNotNone(results, f"{token} was not matched by the regex")

    def test_regex_matches_multiple_valid(self):
        """Should support multiple matches in the middle of a string."""
        token_1 = "NDY3MjIzMjMwNjUwNzc3NjQx.XsyWGg.uFNEQPCc4ePwGh7egG8UicQssz8"
        token_2 = "NDcyMjY1OTQzMDYyNDEzMzMy.XsyWMw.l8XPnDqb0lp-EiQ2g_0xVFT1pyc"
        message = f"garbage {token_1} hello {token_2} world"

        results = token_remover.TOKEN_RE.finditer(message)
        results = [match[0] for match in results]
        self.assertCountEqual((token_1, token_2), results)

    @autospec("bot.cogs.token_remover", "LOG_MESSAGE", "DECODED_LOG_MESSAGE")
    def test_format_log_message(self, log_message, decoded_log_message):
        """Should correctly format the log message with info from the message and token."""
        token = Token("NDcyMjY1OTQzMDYyNDEzMzMy", "XsySD_", "s45jqDV_Iisn-symw0yDRrk_jf4")
        log_message.format.return_value = "Howdy"
        decoded_log_message.format.return_value = " Partner"

        return_value = TokenRemover.format_log_message(self.msg, token, 472265943062413332, None)

        self.assertEqual(
            return_value,
            log_message.format.return_value + "\n" + decoded_log_message.format.return_value,
        )
        log_message.format.assert_called_once_with(
            author=self.msg.author,
            author_id=self.msg.author.id,
            channel=self.msg.channel.mention,
            user_id=token.user_id,
            timestamp=token.timestamp,
            hmac="x" * len(token.hmac),
        )

    @autospec("bot.cogs.token_remover", "LOG_MESSAGE", "USER_TOKEN_MESSAGE")
    def test_format_log_message_user_token(self, log_message, user_token_message):
        """Should correctly format the log message with info from the message and token."""
        token = Token("NDY3MjIzMjMwNjUwNzc3NjQx", "XsySD_", "s45jqDV_Iisn-symw0yDRrk_jf4")
        log_message.format.return_value = "Howdy"
        user_token_message.format.return_value = "Partner"

        return_value = TokenRemover.format_log_message(self.msg, token, 467223230650777641, "Bob")

        self.assertEqual(
            return_value,
            log_message.format.return_value + "\n" + user_token_message.format.return_value,
        )
        log_message.format.assert_called_once_with(
            author=self.msg.author,
            author_id=self.msg.author.id,
            channel=self.msg.channel.mention,
            user_id=token.user_id,
            timestamp=token.timestamp,
            hmac="x" * len(token.hmac),
        )
        user_token_message.format.assert_called_once_with(
            user_id=467223230650777641,
            user_name="Bob",
        )

    @mock.patch.object(TokenRemover, "mod_log", new_callable=mock.PropertyMock)
    @autospec("bot.cogs.token_remover", "log")
    @autospec(TokenRemover, "format_log_message")
    async def test_take_action(self, format_log_message, logger, mod_log_property):
        """Should delete the message and send a mod log."""
        cog = TokenRemover(self.bot)
        mod_log = mock.create_autospec(ModLog, spec_set=True, instance=True)
        token = mock.create_autospec(Token, spec_set=True, instance=True)
        token.user_id = "no-id"
        log_msg = "testing123"

        mod_log_property.return_value = mod_log
        format_log_message.return_value = log_msg

        await cog.take_action(self.msg, token)

        self.msg.delete.assert_called_once_with()
        self.msg.channel.send.assert_called_once_with(
            token_remover.DELETION_MESSAGE_TEMPLATE.format(mention=self.msg.author.mention)
        )

        format_log_message.assert_called_once_with(self.msg, token, None, "Bob")
        logger.debug.assert_called_with(log_msg)
        self.bot.stats.incr.assert_called_once_with("tokens.removed_tokens")

        mod_log.ignore.assert_called_once_with(constants.Event.message_delete, self.msg.id)
        mod_log.send_log_message.assert_called_once_with(
            icon_url=constants.Icons.token_removed,
            colour=Colour(constants.Colours.soft_red),
            title="Token removed!",
            text=log_msg,
            thumbnail=self.msg.author.avatar_url_as.return_value,
            channel_id=constants.Channels.mod_alerts,
            ping_everyone=True,
        )

    @mock.patch.object(TokenRemover, "mod_log", new_callable=mock.PropertyMock)
    async def test_take_action_delete_failure(self, mod_log_property):
        """Shouldn't send any messages if the token message can't be deleted."""
        cog = TokenRemover(self.bot)
        mod_log_property.return_value = mock.create_autospec(ModLog, spec_set=True, instance=True)
        self.msg.delete.side_effect = NotFound(MagicMock(), MagicMock())

        token = mock.create_autospec(Token, spec_set=True, instance=True)
        await cog.take_action(self.msg, token)

        self.msg.delete.assert_called_once_with()
        self.msg.channel.send.assert_not_awaited()


class TokenRemoverExtensionTests(unittest.TestCase):
    """Tests for the token_remover extension."""

    @autospec("bot.cogs.token_remover", "TokenRemover")
    def test_extension_setup(self, cog):
        """The TokenRemover cog should be added."""
        bot = MockBot()
        token_remover.setup(bot)

        cog.assert_called_once_with(bot)
        bot.add_cog.assert_called_once()
        self.assertTrue(isinstance(bot.add_cog.call_args.args[0], TokenRemover))
