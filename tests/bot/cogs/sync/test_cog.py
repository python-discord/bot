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

        self.role_syncer_patcher = mock.patch("bot.cogs.sync.syncers.RoleSyncer", autospec=True)
        self.user_syncer_patcher = mock.patch("bot.cogs.sync.syncers.UserSyncer", autospec=True)
        self.RoleSyncer = self.role_syncer_patcher.start()
        self.UserSyncer = self.user_syncer_patcher.start()

        self.cog = sync.Sync(self.bot)

    def tearDown(self):
        self.role_syncer_patcher.stop()
        self.user_syncer_patcher.stop()

    def test_sync_cog_init(self):
        """Should instantiate syncers and run a sync for the guild."""
        # Reset because a Sync cog was already instantiated in setUp.
        self.RoleSyncer.reset_mock()
        self.UserSyncer.reset_mock()
        self.bot.loop.create_task.reset_mock()

        mock_sync_guild_coro = mock.MagicMock()
        sync.Sync.sync_guild = mock.MagicMock(return_value=mock_sync_guild_coro)

        sync.Sync(self.bot)

        self.RoleSyncer.assert_called_once_with(self.bot)
        self.UserSyncer.assert_called_once_with(self.bot)
        self.bot.loop.create_task.assert_called_once_with(mock_sync_guild_coro)
