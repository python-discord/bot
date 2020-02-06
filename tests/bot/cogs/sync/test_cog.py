import asyncio
import unittest
from unittest import mock

import discord

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


class SyncCogTestCase(unittest.TestCase):
    """Base class for Sync cog tests. Sets up patches for syncers."""

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


class SyncCogTests(SyncCogTestCase):
    """Tests for the Sync cog."""

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

    def patch_user_helper(self, side_effect: BaseException) -> None:
        """Helper to set a side effect for bot.api_client.patch and then assert it is called."""
        self.bot.api_client.patch.reset_mock(side_effect=True)
        self.bot.api_client.patch.side_effect = side_effect

        user_id, updated_information = 5, {"key": 123}
        asyncio.run(self.cog.patch_user(user_id, updated_information))

        self.bot.api_client.patch.assert_called_once_with(
            f"bot/users/{user_id}",
            json=updated_information,
        )

    def test_sync_cog_patch_user(self):
        """A PATCH request should be sent and 404 errors ignored."""
        for side_effect in (None, self.response_error(404)):
            with self.subTest(side_effect=side_effect):
                self.patch_user_helper(side_effect)

    def test_sync_cog_patch_user_non_404(self):
        """A PATCH request should be sent and the error raised if it's not a 404."""
        with self.assertRaises(ResponseCodeError):
            self.patch_user_helper(self.response_error(500))


class SyncCogListenerTests(SyncCogTestCase):
    """Tests for the listeners of the Sync cog."""
    def setUp(self):
        super().setUp()
        self.cog.patch_user = helpers.AsyncMock(spec_set=self.cog.patch_user)

    def test_sync_cog_on_guild_role_create(self):
        """A POST request should be sent with the new role's data."""
        role_data = {
            "colour": 49,
            "id": 777,
            "name": "rolename",
            "permissions": 8,
            "position": 23,
        }
        role = helpers.MockRole(**role_data)
        asyncio.run(self.cog.on_guild_role_create(role))

        self.bot.api_client.post.assert_called_once_with("bot/roles", json=role_data)

    def test_sync_cog_on_guild_role_delete(self):
        """A DELETE request should be sent."""
        role = helpers.MockRole(id=99)
        asyncio.run(self.cog.on_guild_role_delete(role))

        self.bot.api_client.delete.assert_called_once_with("bot/roles/99")

    def test_sync_cog_on_guild_role_update(self):
        """A PUT request should be sent if the colour, name, permissions, or position changes."""
        role_data = {
            "colour": 49,
            "id": 777,
            "name": "rolename",
            "permissions": 8,
            "position": 23,
        }
        subtests = (
            (True, ("colour", "name", "permissions", "position")),
            (False, ("hoist", "mentionable")),
        )

        for should_put, attributes in subtests:
            for attribute in attributes:
                with self.subTest(should_put=should_put, changed_attribute=attribute):
                    self.bot.api_client.put.reset_mock()

                    after_role_data = role_data.copy()
                    after_role_data[attribute] = 876

                    before_role = helpers.MockRole(**role_data)
                    after_role = helpers.MockRole(**after_role_data)

                    asyncio.run(self.cog.on_guild_role_update(before_role, after_role))

                    if should_put:
                        self.bot.api_client.put.assert_called_once_with(
                            f"bot/roles/{after_role.id}",
                            json=after_role_data
                        )
                    else:
                        self.bot.api_client.put.assert_not_called()

    def test_sync_cog_on_member_remove(self):
        """A PUT request should be sent to set in_guild as False and update other fields."""
        roles = [helpers.MockRole(id=i) for i in (57, 22, 43)]  # purposefully unsorted
        member = helpers.MockMember(roles=roles)

        asyncio.run(self.cog.on_member_remove(member))

        json_data = {
            "avatar_hash": member.avatar,
            "discriminator": int(member.discriminator),
            "id": member.id,
            "in_guild": False,
            "name": member.name,
            "roles": sorted(role.id for role in member.roles)
        }
        self.bot.api_client.put.assert_called_once_with(f"bot/users/{member.id}", json=json_data)

    def test_sync_cog_on_member_update_roles(self):
        """Members should be patched if their roles have changed."""
        before_roles = [helpers.MockRole(id=12), helpers.MockRole(id=30)]
        before_member = helpers.MockMember(roles=before_roles)
        after_member = helpers.MockMember(roles=before_roles[1:])

        asyncio.run(self.cog.on_member_update(before_member, after_member))

        data = {"roles": sorted(role.id for role in after_member.roles)}
        self.cog.patch_user.assert_called_once_with(after_member.id, updated_information=data)

    def test_sync_cog_on_member_update_other(self):
        """Members should not be patched if other attributes have changed."""
        subtests = (
            ("activities", discord.Game("Pong"), discord.Game("Frogger")),
            ("nick", "old nick", "new nick"),
            ("status", discord.Status.online, discord.Status.offline),
        )

        for attribute, old_value, new_value in subtests:
            with self.subTest(attribute=attribute):
                self.cog.patch_user.reset_mock()

                before_member = helpers.MockMember(**{attribute: old_value})
                after_member = helpers.MockMember(**{attribute: new_value})

                asyncio.run(self.cog.on_member_update(before_member, after_member))

                self.cog.patch_user.assert_not_called()

    def test_sync_cog_on_user_update(self):
        """A user should be patched only if the name, discriminator, or avatar changes."""
        before_data = {
            "name": "old name",
            "discriminator": "1234",
            "avatar": "old avatar",
            "bot": False,
        }

        subtests = (
            (True, "name", "name", "new name", "new name"),
            (True, "discriminator", "discriminator", "8765", 8765),
            (True, "avatar", "avatar_hash", "9j2e9", "9j2e9"),
            (False, "bot", "bot", True, True),
        )

        for should_patch, attribute, api_field, value, api_value in subtests:
            with self.subTest(attribute=attribute):
                self.cog.patch_user.reset_mock()

                after_data = before_data.copy()
                after_data[attribute] = value
                before_user = helpers.MockUser(**before_data)
                after_user = helpers.MockUser(**after_data)

                asyncio.run(self.cog.on_user_update(before_user, after_user))

                if should_patch:
                    self.cog.patch_user.assert_called_once()

                    # Don't care if *all* keys are present; only the changed one is required
                    call_args = self.cog.patch_user.call_args
                    self.assertEqual(call_args[0][0], after_user.id)
                    self.assertIn("updated_information", call_args[1])

                    updated_information = call_args[1]["updated_information"]
                    self.assertIn(api_field, updated_information)
                    self.assertEqual(updated_information[api_field], api_value)
                else:
                    self.cog.patch_user.assert_not_called()


class SyncCogCommandTests(SyncCogTestCase):
    def test_sync_roles_command(self):
        """sync() should be called on the RoleSyncer."""
        ctx = helpers.MockContext()
        asyncio.run(self.cog.sync_roles_command.callback(self.cog, ctx))

        self.cog.role_syncer.sync.assert_called_once_with(ctx.guild, ctx)
