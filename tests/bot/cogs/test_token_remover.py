import unittest
from unittest import mock
from unittest.mock import MagicMock

from discord import Colour

from bot import constants
from bot.cogs import token_remover
from bot.cogs.moderation import ModLog
from bot.cogs.token_remover import TokenRemover
from tests.helpers import MockBot, MockMessage, autospec


class TokenRemoverTests(unittest.IsolatedAsyncioTestCase):
    """Tests the `TokenRemover` cog."""

    def setUp(self):
        """Adds the cog, a bot, and a message to the instance for usage in tests."""
        self.bot = MockBot()
        self.cog = TokenRemover(bot=self.bot)

        self.msg = MockMessage(id=555, content="hello world")
        self.msg.channel.mention = "#lemonade-stand"
        self.msg.author.__str__ = MagicMock(return_value=self.msg.author.name)
        self.msg.author.avatar_url_as.return_value = "picture-lemon.png"

    def test_is_valid_user_id(self):
        """Should correctly discern valid user IDs and ignore non-numeric and non-ASCII IDs."""
        subtests = (
            ("MTIz", True),  # base64(123)
            ("YWJj", False),  # base64(abc)
            ("λδµ", False),
        )

        for user_id, is_valid in subtests:
            with self.subTest(user_id=user_id, is_valid=is_valid):
                result = TokenRemover.is_valid_user_id(user_id)
                self.assertIs(result, is_valid)

    def test_is_valid_timestamp(self):
        """Should correctly discern valid timestamps."""
        subtests = (
            ("DN9r_A", True),
            ("MTIz", False),  # base64(123)
            ("λδµ", False),
        )

        for timestamp, is_valid in subtests:
            with self.subTest(timestamp=timestamp, is_valid=is_valid):
                result = TokenRemover.is_valid_timestamp(timestamp)
                self.assertIs(result, is_valid)

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

    @autospec("bot.cogs.token_remover", "TOKEN_RE")
    def test_find_token_ignores_bot_messages(self, token_re):
        """The token finder should ignore messages authored by bots."""
        self.msg.author.bot = True

        return_value = TokenRemover.find_token_in_message(self.msg)

        self.assertIsNone(return_value)
        token_re.findall.assert_not_called()

    @autospec(TokenRemover, "is_maybe_token")
    @autospec("bot.cogs.token_remover", "TOKEN_RE")
    def test_find_token_no_matches_returns_none(self, token_re, is_maybe_token):
        """None should be returned if the regex matches no tokens in a message."""
        token_re.findall.return_value = ()

        return_value = TokenRemover.find_token_in_message(self.msg)

        self.assertIsNone(return_value)
        token_re.findall.assert_called_once_with(self.msg.content)
        is_maybe_token.assert_not_called()

    @autospec(TokenRemover, "is_maybe_token")
    @autospec("bot.cogs.token_remover", "TOKEN_RE")
    def test_find_token_returns_found_token(self, token_re, is_maybe_token):
        """The found token should be returned."""
        true_index = 1
        matches = ("foo", "bar", "baz")
        side_effects = [False] * len(matches)
        side_effects[true_index] = True

        token_re.findall.return_value = matches
        is_maybe_token.side_effect = side_effects

        return_value = TokenRemover.find_token_in_message(self.msg)

        self.assertEqual(return_value, matches[true_index])
        token_re.findall.assert_called_once_with(self.msg.content)

        # assert_has_calls isn't used cause it'd allow for extra calls before or after.
        # The function should short-circuit, so nothing past true_index should have been used.
        calls = [mock.call(match) for match in matches[:true_index + 1]]
        self.assertEqual(is_maybe_token.mock_calls, calls)

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
            "'.'.'",
            '"."."',
            "(.(.(",
            ").).)"
        )

        for token in tokens:
            with self.subTest(token=token):
                results = token_remover.TOKEN_RE.findall(token)
                self.assertEqual(len(results), 0)

    def test_regex_valid_tokens(self):
        """Messages that look like tokens should be matched."""
        # Don't worry, the token's been invalidated.
        tokens = (
            "x1.y2.z_3",
            "NDcyMjY1OTQzMDYyNDEzMzMy.Xrim9Q.Ysnu2wacjaKs7qnoo46S8Dm2us8"
        )

        for token in tokens:
            with self.subTest(token=token):
                results = token_remover.TOKEN_RE.findall(token)
                self.assertIn(token, results)

    def test_regex_matches_multiple_valid(self):
        """Should support multiple matches in the middle of a string."""
        tokens = ["x.y.z", "a.b.c"]
        message = f"garbage {tokens[0]} hello {tokens[1]} world"

        results = token_remover.TOKEN_RE.findall(message)
        self.assertEqual(tokens, results)

    @autospec(TokenRemover, "is_valid_user_id", "is_valid_timestamp")
    def test_is_maybe_token_missing_part_returns_false(self, valid_user, valid_time):
        """False should be returned for tokens which do not have all 3 parts."""
        return_value = TokenRemover.is_maybe_token("x.y")

        self.assertFalse(return_value)
        valid_user.assert_not_called()
        valid_time.assert_not_called()

    @autospec(TokenRemover, "is_valid_user_id", "is_valid_timestamp")
    def test_is_maybe_token(self, valid_user, valid_time):
        """Should return True if the user ID and timestamp are valid or return False otherwise."""
        subtests = (
            (False, True, False),
            (True, False, False),
            (True, True, True),
        )

        for user_return, time_return, expected in subtests:
            valid_user.reset_mock()
            valid_time.reset_mock()

            with self.subTest(user_return=user_return, time_return=time_return, expected=expected):
                valid_user.return_value = user_return
                valid_time.return_value = time_return

                actual = TokenRemover.is_maybe_token("x.y.z")
                self.assertIs(actual, expected)

                valid_user.assert_called_once_with("x")
                if user_return:
                    valid_time.assert_called_once_with("y")

    async def test_delete_message(self):
        """The message should be deleted, and a message should be sent to the same channel."""
        await TokenRemover.delete_message(self.msg)

        self.msg.delete.assert_called_once_with()
        self.msg.channel.send.assert_called_once_with(
            token_remover.DELETION_MESSAGE_TEMPLATE.format(mention=self.msg.author.mention)
        )

    @autospec("bot.cogs.token_remover", "LOG_MESSAGE")
    async def test_format_log_message(self, log_message):
        """Should correctly format the log message with info from the message and token."""
        log_message.format.return_value = "Howdy"
        return_value = TokenRemover.format_log_message(self.msg, "MTIz.DN9R_A.xyz")

        self.assertEqual(return_value, log_message.format.return_value)
        log_message.format.assert_called_once_with(
            author=self.msg.author,
            author_id=self.msg.author.id,
            channel=self.msg.channel.mention,
            user_id="MTIz",
            timestamp="DN9R_A",
            hmac="xxx",
        )

    @mock.patch.object(TokenRemover, "mod_log", new_callable=mock.PropertyMock)
    @autospec("bot.cogs.token_remover", "log")
    @autospec(TokenRemover, "delete_message", "format_log_message")
    async def test_take_action(self, delete_message, format_log_message, logger, mod_log_property):
        """Should delete the message and send a mod log."""
        cog = TokenRemover(self.bot)
        mod_log = mock.create_autospec(ModLog, spec_set=True, instance=True)
        token = "MTIz.DN9R_A.xyz"
        log_msg = "testing123"

        mod_log_property.return_value = mod_log
        format_log_message.return_value = log_msg

        await cog.take_action(self.msg, token)

        delete_message.assert_awaited_once_with(self.msg)
        format_log_message.assert_called_once_with(self.msg, token)
        logger.debug.assert_called_with(log_msg)
        self.bot.stats.incr.assert_called_once_with("tokens.removed_tokens")

        mod_log.ignore.assert_called_once_with(constants.Event.message_delete, self.msg.id)
        mod_log.send_log_message.assert_called_once_with(
            icon_url=constants.Icons.token_removed,
            colour=Colour(constants.Colours.soft_red),
            title="Token removed!",
            text=log_msg,
            thumbnail=self.msg.author.avatar_url_as.return_value,
            channel_id=constants.Channels.mod_alerts
        )


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
