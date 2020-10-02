import unittest
from unittest import mock


from bot.api import ResponseCodeError
from bot.exts.backend.sync._syncers import Syncer
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


class SyncerSyncTests(unittest.IsolatedAsyncioTestCase):
    """Tests for main function orchestrating the sync."""

    def setUp(self):
        self.bot = helpers.MockBot(user=helpers.MockMember(bot=True))
        self.syncer = TestSyncer(self.bot)
        self.guild = helpers.MockGuild()

        # Make sure `_get_diff` returns a MagicMock, not an AsyncMock
        self.syncer._get_diff.return_value = mock.MagicMock()

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
                ctx = helpers.MockContext()
                ctx.send.return_value = message

                await self.syncer.sync(self.guild, ctx)

                if should_edit:
                    message.edit.assert_called_once()
                    self.assertIn("content", message.edit.call_args[1])

    async def test_sync_message_sent(self):
        """If ctx is given, a new message should be sent."""
        subtests = (
            (None, None),
            (helpers.MockContext(), helpers.MockMessage()),
        )

        for ctx, message in subtests:
            with self.subTest(ctx=ctx, message=message):
                await self.syncer.sync(self.guild, ctx)

                if ctx is not None:
                    ctx.send.assert_called_once()
