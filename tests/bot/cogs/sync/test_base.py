import asyncio
import unittest
from unittest import mock

import discord

from bot import constants
from bot.api import ResponseCodeError
from bot.cogs.sync.syncers import Syncer, _Diff
from tests import helpers


class TestSyncer(Syncer):
    """Syncer subclass with mocks for abstract methods for testing purposes."""

    name = "test"
    _get_diff = mock.AsyncMock()
    _sync = mock.AsyncMock()


class SyncerBaseTests(unittest.TestCase):
    """Tests for the syncer base class."""

    def setUp(self):
        self.bot = helpers.MockBot()

    def test_instantiation_fails_without_abstract_methods(self):
        """The class must have abstract methods implemented."""
        with self.assertRaisesRegex(TypeError, "Can't instantiate abstract class"):
            Syncer(self.bot)


class SyncerSendPromptTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_send_prompt_edits_and_returns_message(self):
        """The given message should be edited to display the prompt and then should be returned."""
        msg = helpers.MockMessage()
        ret_val = await self.syncer._send_prompt(msg)

        msg.edit.assert_called_once()
        self.assertIn("content", msg.edit.call_args[1])
        self.assertEqual(ret_val, msg)

    async def test_send_prompt_gets_dev_core_channel(self):
        """The dev-core channel should be retrieved if an extant message isn't given."""
        subtests = (
            (self.bot.get_channel, self.mock_get_channel),
            (self.bot.fetch_channel, self.mock_fetch_channel),
        )

        for method, mock_ in subtests:
            with self.subTest(method=method, msg=mock_.__name__):
                mock_()
                await self.syncer._send_prompt()

                method.assert_called_once_with(constants.Channels.dev_core)

    async def test_send_prompt_returns_none_if_channel_fetch_fails(self):
        """None should be returned if there's an HTTPException when fetching the channel."""
        self.bot.get_channel.return_value = None
        self.bot.fetch_channel.side_effect = discord.HTTPException(mock.MagicMock(), "test error!")

        ret_val = await self.syncer._send_prompt()

        self.assertIsNone(ret_val)

    async def test_send_prompt_sends_and_returns_new_message_if_not_given(self):
        """A new message mentioning core devs should be sent and returned if message isn't given."""
        for mock_ in (self.mock_get_channel, self.mock_fetch_channel):
            with self.subTest(msg=mock_.__name__):
                mock_channel, mock_message = mock_()
                ret_val = await self.syncer._send_prompt()

                mock_channel.send.assert_called_once()
                self.assertIn(self.syncer._CORE_DEV_MENTION, mock_channel.send.call_args[0][0])
                self.assertEqual(ret_val, mock_message)

    async def test_send_prompt_adds_reactions(self):
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
                await self.syncer._send_prompt(message_arg)

                calls = [mock.call(emoji) for emoji in self.syncer._REACTION_EMOJIS]
                mock_message.add_reaction.assert_has_calls(calls)


class SyncerConfirmationTests(unittest.IsolatedAsyncioTestCase):
    """Tests for waiting for a sync confirmation reaction on the prompt."""

    def setUp(self):
        self.bot = helpers.MockBot()
        self.syncer = TestSyncer(self.bot)
        self.core_dev_role = helpers.MockRole(id=constants.Roles.core_developers)

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

    async def test_wait_for_confirmation(self):
        """The message should always be edited and only return True if the emoji is a check mark."""
        subtests = (
            (constants.Emojis.check_mark, True, None),
            ("InVaLiD", False, None),
            (None, False, asyncio.TimeoutError),
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
                    actual_return = await self.syncer._wait_for_confirmation(member, message)

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


class SyncerSyncTests(unittest.IsolatedAsyncioTestCase):
    """Tests for main function orchestrating the sync."""

    def setUp(self):
        self.bot = helpers.MockBot(user=helpers.MockMember(bot=True))
        self.syncer = TestSyncer(self.bot)

    async def test_sync_respects_confirmation_result(self):
        """The sync should abort if confirmation fails and continue if confirmed."""
        mock_message = helpers.MockMessage()
        subtests = (
            (True, mock_message),
            (False, None),
        )

        for confirmed, message in subtests:
            with self.subTest(confirmed=confirmed):
                self.syncer._sync.reset_mock()
                self.syncer._get_diff.reset_mock()

                diff = _Diff({1, 2, 3}, {4, 5}, None)
                self.syncer._get_diff.return_value = diff
                self.syncer._get_confirmation_result = mock.AsyncMock(
                    return_value=(confirmed, message)
                )

                guild = helpers.MockGuild()
                await self.syncer.sync(guild)

                self.syncer._get_diff.assert_called_once_with(guild)
                self.syncer._get_confirmation_result.assert_called_once()

                if confirmed:
                    self.syncer._sync.assert_called_once_with(diff)
                else:
                    self.syncer._sync.assert_not_called()

    async def test_sync_diff_size(self):
        """The diff size should be correctly calculated."""
        subtests = (
            (6, _Diff({1, 2}, {3, 4}, {5, 6})),
            (5, _Diff({1, 2, 3}, None, {4, 5})),
            (0, _Diff(None, None, None)),
            (0, _Diff(set(), set(), set())),
        )

        for size, diff in subtests:
            with self.subTest(size=size, diff=diff):
                self.syncer._get_diff.reset_mock()
                self.syncer._get_diff.return_value = diff
                self.syncer._get_confirmation_result = mock.AsyncMock(return_value=(False, None))

                guild = helpers.MockGuild()
                await self.syncer.sync(guild)

                self.syncer._get_diff.assert_called_once_with(guild)
                self.syncer._get_confirmation_result.assert_called_once()
                self.assertEqual(self.syncer._get_confirmation_result.call_args[0][0], size)

    async def test_sync_message_edited(self):
        """The message should be edited if one was sent, even if the sync has an API error."""
        subtests = (
            (None, None, False),
            (helpers.MockMessage(), None, True),
            (helpers.MockMessage(), ResponseCodeError(mock.MagicMock()), True),
        )

        for message, side_effect, should_edit in subtests:
            with self.subTest(message=message, side_effect=side_effect, should_edit=should_edit):
                self.syncer._sync.side_effect = side_effect
                self.syncer._get_confirmation_result = mock.AsyncMock(
                    return_value=(True, message)
                )

                guild = helpers.MockGuild()
                await self.syncer.sync(guild)

                if should_edit:
                    message.edit.assert_called_once()
                    self.assertIn("content", message.edit.call_args[1])

    async def test_sync_confirmation_context_redirect(self):
        """If ctx is given, a new message should be sent and author should be ctx's author."""
        mock_member = helpers.MockMember()
        subtests = (
            (None, self.bot.user, None),
            (helpers.MockContext(author=mock_member), mock_member, helpers.MockMessage()),
        )

        for ctx, author, message in subtests:
            with self.subTest(ctx=ctx, author=author, message=message):
                if ctx is not None:
                    ctx.send.return_value = message

                # Make sure `_get_diff` returns a MagicMock, not an AsyncMock
                self.syncer._get_diff.return_value = mock.MagicMock()

                self.syncer._get_confirmation_result = mock.AsyncMock(return_value=(False, None))

                guild = helpers.MockGuild()
                await self.syncer.sync(guild, ctx)

                if ctx is not None:
                    ctx.send.assert_called_once()

                self.syncer._get_confirmation_result.assert_called_once()
                self.assertEqual(self.syncer._get_confirmation_result.call_args[0][1], author)
                self.assertEqual(self.syncer._get_confirmation_result.call_args[0][2], message)

    @mock.patch.object(constants.Sync, "max_diff", new=3)
    async def test_confirmation_result_small_diff(self):
        """Should always return True and the given message if the diff size is too small."""
        author = helpers.MockMember()
        expected_message = helpers.MockMessage()

        for size in (3, 2):  # pragma: no cover
            with self.subTest(size=size):
                self.syncer._send_prompt = mock.AsyncMock()
                self.syncer._wait_for_confirmation = mock.AsyncMock()

                coro = self.syncer._get_confirmation_result(size, author, expected_message)
                result, actual_message = await coro

                self.assertTrue(result)
                self.assertEqual(actual_message, expected_message)
                self.syncer._send_prompt.assert_not_called()
                self.syncer._wait_for_confirmation.assert_not_called()

    @mock.patch.object(constants.Sync, "max_diff", new=3)
    async def test_confirmation_result_large_diff(self):
        """Should return True if confirmed and False if _send_prompt fails or aborted."""
        author = helpers.MockMember()
        mock_message = helpers.MockMessage()

        subtests = (
            (True, mock_message, True, "confirmed"),
            (False, None, False, "_send_prompt failed"),
            (False, mock_message, False, "aborted"),
        )

        for expected_result, expected_message, confirmed, msg in subtests:  # pragma: no cover
            with self.subTest(msg=msg):
                self.syncer._send_prompt = mock.AsyncMock(return_value=expected_message)
                self.syncer._wait_for_confirmation = mock.AsyncMock(return_value=confirmed)

                coro = self.syncer._get_confirmation_result(4, author)
                actual_result, actual_message = await coro

                self.syncer._send_prompt.assert_called_once_with(None)  # message defaults to None
                self.assertIs(actual_result, expected_result)
                self.assertEqual(actual_message, expected_message)

                if expected_message:
                    self.syncer._wait_for_confirmation.assert_called_once_with(
                        author, expected_message
                    )
