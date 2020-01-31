import asyncio
import unittest
from unittest import mock

from bot import constants
from bot.api import ResponseCodeError
from bot.cogs import sync
from bot.cogs.sync.syncers import Syncer
from tests import helpers


class MockSyncer(helpers.CustomMockMixin, mock.MagicMock):
    """
    A MagicMock subclass to mock Syncer objects.

    Instances of this class will follow the specifications of `bot.cogs.sync.syncers.Syncer`
    instances. For more information, see the `MockGuild` docstring.
    """
    def __init__(self, **kwargs) -> None:
        super().__init__(spec_set=Syncer, **kwargs)


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

        # These patch the type. When the type is called, a MockSyncer instanced is returned.
        # MockSyncer is needed so that our custom AsyncMock is used.
        # TODO: Use autospec instead in 3.8, which will automatically use AsyncMock when needed.
        self.role_syncer_patcher = mock.patch(
            "bot.cogs.sync.syncers.RoleSyncer",
            new=mock.MagicMock(return_value=MockSyncer())
        )
        self.user_syncer_patcher = mock.patch(
            "bot.cogs.sync.syncers.UserSyncer",
            new=mock.MagicMock(return_value=MockSyncer())
        )
        self.RoleSyncer = self.role_syncer_patcher.start()
        self.UserSyncer = self.user_syncer_patcher.start()

        self.cog = sync.Sync(self.bot)

    def tearDown(self):
        self.role_syncer_patcher.stop()
        self.user_syncer_patcher.stop()

    @staticmethod
    def response_error(status: int) -> ResponseCodeError:
        """Fixture to return a ResponseCodeError with the given status code."""
        response = mock.MagicMock()
        response.status = status

        return ResponseCodeError(response)

    @mock.patch.object(sync.Sync, "sync_guild")
    def test_sync_cog_init(self, sync_guild):
        """Should instantiate syncers and run a sync for the guild."""
        # Reset because a Sync cog was already instantiated in setUp.
        self.RoleSyncer.reset_mock()
        self.UserSyncer.reset_mock()
        self.bot.loop.create_task.reset_mock()

        mock_sync_guild_coro = mock.MagicMock()
        sync_guild.return_value = mock_sync_guild_coro

        sync.Sync(self.bot)

        self.RoleSyncer.assert_called_once_with(self.bot)
        self.UserSyncer.assert_called_once_with(self.bot)
        sync_guild.assert_called_once_with()
        self.bot.loop.create_task.assert_called_once_with(mock_sync_guild_coro)

    def test_sync_cog_sync_guild(self):
        """Roles and users should be synced only if a guild is successfully retrieved."""
        for guild in (helpers.MockGuild(), None):
            with self.subTest(guild=guild):
                self.bot.reset_mock()
                self.cog.role_syncer.reset_mock()
                self.cog.user_syncer.reset_mock()

                self.bot.get_guild = mock.MagicMock(return_value=guild)

                asyncio.run(self.cog.sync_guild())

                self.bot.wait_until_guild_available.assert_called_once()
                self.bot.get_guild.assert_called_once_with(constants.Guild.id)

                if guild is None:
                    self.cog.role_syncer.sync.assert_not_called()
                    self.cog.user_syncer.sync.assert_not_called()
                else:
                    self.cog.role_syncer.sync.assert_called_once_with(guild)
                    self.cog.user_syncer.sync.assert_called_once_with(guild)

    def test_sync_cog_patch_user(self):
        """A PATCH request should be sent and 404 errors ignored."""
        for side_effect in (None, self.response_error(404)):
            with self.subTest(side_effect=side_effect):
                self.bot.api_client.patch.reset_mock(side_effect=True)
                self.bot.api_client.patch.side_effect = side_effect

                asyncio.run(self.cog.patch_user(5, {}))
                self.bot.api_client.patch.assert_called_once()

    def test_sync_cog_patch_user_non_404(self):
        """A PATCH request should be sent and the error raised if it's not a 404."""
        self.bot.api_client.patch.side_effect = self.response_error(500)
        with self.assertRaises(ResponseCodeError):
            asyncio.run(self.cog.patch_user(5, {}))
            self.bot.api_client.patch.assert_called_once()
