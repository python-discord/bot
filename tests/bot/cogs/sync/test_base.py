import asyncio
import unittest

from bot.cogs.sync.syncers import Syncer
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
        self.syncer = TestSyncer(self.bot)

    def test_instantiation_fails_without_abstract_methods(self):
        """The class must have abstract methods implemented."""
        with self.assertRaisesRegex(TypeError, "Can't instantiate abstract class"):
            Syncer(self.bot)

    def test_send_prompt_edits_message_content(self):
        """The contents of the given message should be edited to display the prompt."""
        msg = helpers.MockMessage()
        asyncio.run(self.syncer._send_prompt(msg))

        msg.edit.assert_called_once()
        self.assertIn("content", msg.edit.call_args[1])
