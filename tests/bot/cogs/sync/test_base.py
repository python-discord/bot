import asyncio
import unittest
from unittest import mock

import discord

from bot import constants
from bot.cogs.sync.syncers import Syncer, _Diff
from tests import helpers


class TestSyncer(Syncer):
    """Syncer subclass with mocks for abstract methods for testing purposes."""

    name = "test"
    _get_diff = helpers.AsyncMock()
    _sync = helpers.AsyncMock()


class SyncerBaseTests(unittest.TestCase):
    """Tests for the syncer base class."""

    def setUp(self):
        self.bot = helpers.MockBot()

    def test_instantiation_fails_without_abstract_methods(self):
        """The class must have abstract methods implemented."""
        with self.assertRaisesRegex(TypeError, "Can't instantiate abstract class"):
            Syncer(self.bot)


class SyncerSendPromptTests(unittest.TestCase):
    """Tests for sending the sync confirmation prompt."""

    def setUp(self):
        self.bot = helpers.MockBot()
        self.syncer = TestSyncer(self.bot)

    def mock_get_channel(self):
        """Fixture to return a mock channel and message for when `get_channel` is used."""
        self.bot.reset_mock()

        mock_channel = helpers.MockTextChannel()
        mock_message = helpers.MockMessage()

        mock_channel.send.return_value = mock_message
        self.bot.get_channel.return_value = mock_channel

        return mock_channel, mock_message

    def mock_fetch_channel(self):
        """Fixture to return a mock channel and message for when `fetch_channel` is used."""
        self.bot.reset_mock()

        mock_channel = helpers.MockTextChannel()
        mock_message = helpers.MockMessage()

        self.bot.get_channel.return_value = None
        mock_channel.send.return_value = mock_message
        self.bot.fetch_channel.return_value = mock_channel

        return mock_channel, mock_message

    def test_send_prompt_edits_and_returns_message(self):
        """The given message should be edited to display the prompt and then should be returned."""
        msg = helpers.MockMessage()
        ret_val = asyncio.run(self.syncer._send_prompt(msg))

        msg.edit.assert_called_once()
        self.assertIn("content", msg.edit.call_args[1])
        self.assertEqual(ret_val, msg)

    def test_send_prompt_gets_dev_core_channel(self):
        """The dev-core channel should be retrieved if an extant message isn't given."""
        subtests = (
            (self.bot.get_channel, self.mock_get_channel),
            (self.bot.fetch_channel, self.mock_fetch_channel),
        )

        for method, mock_ in subtests:
            with self.subTest(method=method, msg=mock_.__name__):
                mock_()
                asyncio.run(self.syncer._send_prompt())

                method.assert_called_once_with(constants.Channels.devcore)

    def test_send_prompt_returns_None_if_channel_fetch_fails(self):
        """None should be returned if there's an HTTPException when fetching the channel."""
        self.bot.get_channel.return_value = None
        self.bot.fetch_channel.side_effect = discord.HTTPException(mock.MagicMock(), "test error!")

        ret_val = asyncio.run(self.syncer._send_prompt())

        self.assertIsNone(ret_val)

    def test_send_prompt_sends_and_returns_new_message_if_not_given(self):
        """A new message mentioning core devs should be sent and returned if message isn't given."""
        for mock_ in (self.mock_get_channel, self.mock_fetch_channel):
            with self.subTest(msg=mock_.__name__):
                mock_channel, mock_message = mock_()
                ret_val = asyncio.run(self.syncer._send_prompt())

                mock_channel.send.assert_called_once()
                self.assertIn(self.syncer._CORE_DEV_MENTION, mock_channel.send.call_args[0][0])
                self.assertEqual(ret_val, mock_message)

    def test_send_prompt_adds_reactions(self):
        """The message should have reactions for confirmation added."""
        extant_message = helpers.MockMessage()
        subtests = (
            (extant_message, lambda: (None, extant_message)),
            (None, self.mock_get_channel),
            (None, self.mock_fetch_channel),
        )

        for message_arg, mock_ in subtests:
            subtest_msg = "Extant message" if mock_.__name__ == "<lambda>" else mock_.__name__

            with self.subTest(msg=subtest_msg):
                _, mock_message = mock_()
                asyncio.run(self.syncer._send_prompt(message_arg))

                calls = [mock.call(emoji) for emoji in self.syncer._REACTION_EMOJIS]
                mock_message.add_reaction.assert_has_calls(calls)


class SyncerConfirmationTests(unittest.TestCase):
    """Tests for waiting for a sync confirmation reaction on the prompt."""

    def setUp(self):
        self.bot = helpers.MockBot()
        self.syncer = TestSyncer(self.bot)
        self.core_dev_role = helpers.MockRole(id=constants.Roles.core_developer)

    @staticmethod
    def get_message_reaction(emoji):
        """Fixture to return a mock message an reaction from the given `emoji`."""
        message = helpers.MockMessage()
        reaction = helpers.MockReaction(emoji=emoji, message=message)

        return message, reaction

    def test_reaction_check_for_valid_emoji_and_authors(self):
        """Should return True if authors are identical or are a bot and a core dev, respectively."""
        user_subtests = (
            (
                helpers.MockMember(id=77),
                helpers.MockMember(id=77),
                "identical users",
            ),
            (
                helpers.MockMember(id=77, bot=True),
                helpers.MockMember(id=43, roles=[self.core_dev_role]),
                "bot author and core-dev reactor",
            ),
        )

        for emoji in self.syncer._REACTION_EMOJIS:
            for author, user, msg in user_subtests:
                with self.subTest(author=author, user=user, emoji=emoji, msg=msg):
                    message, reaction = self.get_message_reaction(emoji)
                    ret_val = self.syncer._reaction_check(author, message, reaction, user)

                    self.assertTrue(ret_val)

    def test_reaction_check_for_invalid_reactions(self):
        """Should return False for invalid reaction events."""
        valid_emoji = self.syncer._REACTION_EMOJIS[0]
        subtests = (
            (
                helpers.MockMember(id=77),
                *self.get_message_reaction(valid_emoji),
                helpers.MockMember(id=43, roles=[self.core_dev_role]),
                "users are not identical",
            ),
            (
                helpers.MockMember(id=77, bot=True),
                *self.get_message_reaction(valid_emoji),
                helpers.MockMember(id=43),
                "reactor lacks the core-dev role",
            ),
            (
                helpers.MockMember(id=77, bot=True, roles=[self.core_dev_role]),
                *self.get_message_reaction(valid_emoji),
                helpers.MockMember(id=77, bot=True, roles=[self.core_dev_role]),
                "reactor is a bot",
            ),
            (
                helpers.MockMember(id=77),
                helpers.MockMessage(id=95),
                helpers.MockReaction(emoji=valid_emoji, message=helpers.MockMessage(id=26)),
                helpers.MockMember(id=77),
                "messages are not identical",
            ),
            (
                helpers.MockMember(id=77),
                *self.get_message_reaction("InVaLiD"),
                helpers.MockMember(id=77),
                "emoji is invalid",
            ),
        )

        for *args, msg in subtests:
            kwargs = dict(zip(("author", "message", "reaction", "user"), args))
            with self.subTest(**kwargs, msg=msg):
                ret_val = self.syncer._reaction_check(*args)
                self.assertFalse(ret_val)

    def test_wait_for_confirmation(self):
        """The message should always be edited and only return True if the emoji is a check mark."""
        subtests = (
            (constants.Emojis.check_mark, True, None),
            ("InVaLiD", False, None),
            (None, False, TimeoutError),
        )

        for emoji, ret_val, side_effect in subtests:
            for bot in (True, False):
                with self.subTest(emoji=emoji, ret_val=ret_val, side_effect=side_effect, bot=bot):
                    # Set up mocks
                    message = helpers.MockMessage()
                    member = helpers.MockMember(bot=bot)

                    self.bot.wait_for.reset_mock()
                    self.bot.wait_for.return_value = (helpers.MockReaction(emoji=emoji), None)
                    self.bot.wait_for.side_effect = side_effect

                    # Call the function
                    actual_return = asyncio.run(self.syncer._wait_for_confirmation(member, message))

                    # Perform assertions
                    self.bot.wait_for.assert_called_once()
                    self.assertIn("reaction_add", self.bot.wait_for.call_args[0])

                    message.edit.assert_called_once()
                    kwargs = message.edit.call_args[1]
                    self.assertIn("content", kwargs)

                    # Core devs should only be mentioned if the author is a bot.
                    if bot:
                        self.assertIn(self.syncer._CORE_DEV_MENTION, kwargs["content"])
                    else:
                        self.assertNotIn(self.syncer._CORE_DEV_MENTION, kwargs["content"])

                    self.assertIs(actual_return, ret_val)


class SyncerSyncTests(unittest.TestCase):
    """Tests for main function orchestrating the sync."""

    def setUp(self):
        self.bot = helpers.MockBot()
        self.syncer = TestSyncer(self.bot)

    def test_sync_sends_confirmation_prompt(self):
        """The prompt should be sent only if the diff is large and should fail if not confirmed."""
        large_diff = _Diff({1}, {2}, {3})
        subtests = (
            (False, False, True, None, None, _Diff({1}, {2}, set()), "diff too small"),
            (True, True, True, helpers.MockMessage(), True, large_diff, "confirmed"),
            (True, False, False, None, None, large_diff, "couldn't get channel"),
            (True, True, False, helpers.MockMessage(), False, large_diff, "not confirmed"),
        )

        for prompt_called, wait_called, sync_called, prompt_msg, confirmed, diff, msg in subtests:
            with self.subTest(msg=msg):
                self.syncer._sync.reset_mock()
                self.syncer._get_diff.reset_mock()

                self.syncer.MAX_DIFF = 2
                self.syncer._get_diff.return_value = diff
                self.syncer._send_prompt = helpers.AsyncMock(return_value=prompt_msg)
                self.syncer._wait_for_confirmation = helpers.AsyncMock(return_value=confirmed)

                guild = helpers.MockGuild()
                asyncio.run(self.syncer.sync(guild))

                self.syncer._get_diff.assert_called_once_with(guild)

                if prompt_called:
                    self.syncer._send_prompt.assert_called_once()
                else:
                    self.syncer._send_prompt.assert_not_called()

                if wait_called:
                    self.syncer._wait_for_confirmation.assert_called_once()
                else:
                    self.syncer._wait_for_confirmation.assert_not_called()

                if sync_called:
                    self.syncer._sync.assert_called_once_with(diff)
                else:
                    self.syncer._sync.assert_not_called()
