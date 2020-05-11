import asyncio
import logging
import unittest
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

from discord import Colour

from bot.cogs.token_remover import (
    DELETION_MESSAGE_TEMPLATE,
    TOKEN_RE,
    TokenRemover,
    setup as setup_cog,
)
from bot.constants import Channels, Colours, Event, Icons
from tests.helpers import MockBot, MockMessage, autospec


class TokenRemoverTests(unittest.IsolatedAsyncioTestCase):
    """Tests the `TokenRemover` cog."""

    def setUp(self):
        """Adds the cog, a bot, and a message to the instance for usage in tests."""
        self.bot = MockBot()
        self.bot.get_cog.return_value = MagicMock()
        self.bot.get_cog.return_value.send_log_message = AsyncMock()
        self.cog = TokenRemover(bot=self.bot)

        self.msg = MockMessage(id=555, content="hello world")
        self.msg.channel.mention = "#lemonade-stand"
        self.msg.author.__str__ = MagicMock(return_value=self.msg.author.name)
        self.msg.author.avatar_url_as.return_value = "picture-lemon.png"

    def test_is_valid_user_id_is_true_for_numeric_content(self):
        """A string decoding to numeric characters is a valid user ID."""
        # MTIz = base64(123)
        self.assertTrue(TokenRemover.is_valid_user_id('MTIz'))

    def test_is_valid_user_id_is_false_for_alphabetic_content(self):
        """A string decoding to alphabetic characters is not a valid user ID."""
        # YWJj = base64(abc)
        self.assertFalse(TokenRemover.is_valid_user_id('YWJj'))

    def test_is_valid_timestamp_is_true_for_valid_timestamps(self):
        """A string decoding to a valid timestamp should be recognized as such."""
        self.assertTrue(TokenRemover.is_valid_timestamp('DN9r_A'))

    def test_is_valid_timestamp_is_false_for_invalid_values(self):
        """A string not decoding to a valid timestamp should not be recognized as such."""
        # MTIz = base64(123)
        self.assertFalse(TokenRemover.is_valid_timestamp('MTIz'))

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
                results = TOKEN_RE.findall(token)
                self.assertEquals(len(results), 0)

    def test_regex_valid_tokens(self):
        """Messages that look like tokens should be matched."""
        # Don't worry, the token's been invalidated.
        tokens = (
            "x1.y2.z_3",
            "NDcyMjY1OTQzMDYyNDEzMzMy.Xrim9Q.Ysnu2wacjaKs7qnoo46S8Dm2us8"
        )

        for token in tokens:
            with self.subTest(token=token):
                results = TOKEN_RE.findall(token)
                self.assertIn(token, results)

    def test_regex_matches_multiple_valid(self):
        """Should support multiple matches in the middle of a string."""
        tokens = ["x.y.z", "a.b.c"]
        message = f"garbage {tokens[0]} hello {tokens[1]} world"

        results = TOKEN_RE.findall(message)
        self.assertEquals(tokens, results)

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
            DELETION_MESSAGE_TEMPLATE.format(mention=self.msg.author.mention)
        )

    def test_censors_valid_tokens(self):
        """Valid tokens are censored."""
        cases = (
            # (content, censored_token)
            ('MTIz.DN9R_A.xyz', 'MTIz.DN9R_A.xxx'),
        )

        for content, censored_token in cases:
            with self.subTest(content=content, censored_token=censored_token):
                self.msg.content = content
                coroutine = self.cog.on_message(self.msg)
                with self.assertLogs(logger='bot.cogs.token_remover', level=logging.DEBUG) as cm:
                    self.assertIsNone(asyncio.run(coroutine))  # no return value

                [line] = cm.output
                log_message = (
                    "Censored a seemingly valid token sent by "
                    "lemon (`42`) in #lemonade-stand, "
                    f"token was `{censored_token}`"
                )
                self.assertIn(log_message, line)

                self.msg.delete.assert_called_once_with()
                self.msg.channel.send.assert_called_once_with(
                    DELETION_MESSAGE_TEMPLATE.format(mention='@lemon')
                )
                self.bot.get_cog.assert_called_with('ModLog')
                self.msg.author.avatar_url_as.assert_called_once_with(static_format='png')

                mod_log = self.bot.get_cog.return_value
                mod_log.ignore.assert_called_once_with(Event.message_delete, self.msg.id)
                mod_log.send_log_message.assert_called_once_with(
                    icon_url=Icons.token_removed,
                    colour=Colour(Colours.soft_red),
                    title="Token removed!",
                    text=log_message,
                    thumbnail='picture-lemon.png',
                    channel_id=Channels.mod_alerts
                )


class TokenRemoverSetupTests(unittest.TestCase):
    """Tests setup of the `TokenRemover` cog."""

    def test_setup(self):
        """Setup of the extension should call add_cog."""
        bot = MockBot()
        setup_cog(bot)
        bot.add_cog.assert_called_once()
