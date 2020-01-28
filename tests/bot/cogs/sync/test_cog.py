import unittest
from unittest import mock

from bot.cogs import sync
from tests import helpers


class SyncExtensionTests(unittest.TestCase):
    """Tests for the sync extension."""

    @staticmethod
    def test_extension_setup():
        """The Sync cog should be added."""
        bot = helpers.MockBot()
        sync.setup(bot)
        bot.add_cog.assert_called_once()


class SyncCogTests(unittest.TestCase):
    """Tests for the Sync cog."""

    def setUp(self):
        self.bot = helpers.MockBot()

    @mock.patch("bot.cogs.sync.syncers.RoleSyncer", autospec=True)
    @mock.patch("bot.cogs.sync.syncers.UserSyncer", autospec=True)
    def test_sync_cog_init(self, mock_role, mock_sync):
        """Should instantiate syncers and run a sync for the guild."""
        mock_sync_guild_coro = mock.MagicMock()
        sync.Sync.sync_guild = mock.MagicMock(return_value=mock_sync_guild_coro)

        sync.Sync(self.bot)

        mock_role.assert_called_once_with(self.bot)
        mock_sync.assert_called_once_with(self.bot)
        self.bot.loop.create_task.assert_called_once_with(mock_sync_guild_coro)
