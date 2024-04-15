import types
import unittest
import unittest.mock
from unittest import mock

import discord
from pydis_core.site_api import ResponseCodeError

from bot import constants
from bot.exts.backend import sync
from bot.exts.backend.sync._cog import Sync
from bot.exts.backend.sync._syncers import Syncer
from tests import helpers
from tests.base import CommandTestCase


class SyncExtensionTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the sync extension."""

    @staticmethod
    async def test_extension_setup():
        """The Sync cog should be added."""
        bot = helpers.MockBot()
        await sync.setup(bot)
        bot.add_cog.assert_awaited_once()


class SyncCogTestCase(unittest.IsolatedAsyncioTestCase):
    """Base class for Sync cog tests. Sets up patches for syncers."""

    def setUp(self):
        self.bot = helpers.MockBot()

        role_syncer_patcher = mock.patch(
            "bot.exts.backend.sync._syncers.RoleSyncer",
            autospec=Syncer,
            spec_set=True
        )
        user_syncer_patcher = mock.patch(
            "bot.exts.backend.sync._syncers.UserSyncer",
            autospec=Syncer,
            spec_set=True
        )

        self.RoleSyncer = role_syncer_patcher.start()
        self.UserSyncer = user_syncer_patcher.start()

        self.addCleanup(role_syncer_patcher.stop)
        self.addCleanup(user_syncer_patcher.stop)

        self.cog = Sync(self.bot)

    @staticmethod
    def response_error(status: int) -> ResponseCodeError:
        """Fixture to return a ResponseCodeError with the given status code."""
        response = mock.MagicMock()
        response.status = status

        return ResponseCodeError(response)


class SyncCogTests(SyncCogTestCase):
    """Tests for the Sync cog."""

    @unittest.mock.patch("bot.exts.backend.sync._cog.create_task", new_callable=unittest.mock.MagicMock)
    async def test_sync_cog_sync_on_load(self, mock_create_task: unittest.mock.MagicMock):
        """Sync function should be synced on cog load only if guild is found."""
        for guild in (helpers.MockGuild(), None):
            with self.subTest(guild=guild):
                mock_create_task.reset_mock()
                self.bot.reset_mock()
                self.RoleSyncer.reset_mock()
                self.UserSyncer.reset_mock()

                self.bot.get_guild = mock.MagicMock(return_value=guild)
                error_raised = False
                try:
                    await self.cog.cog_load()
                except ValueError:
                    if guild is None:
                        error_raised = True
                    else:
                        raise

                if guild is None:
                    self.assertTrue(error_raised)
                    mock_create_task.assert_not_called()
                else:
                    mock_create_task.assert_called_once()
                    create_task_arg = mock_create_task.call_args[0][0]
                    self.assertIsInstance(create_task_arg, types.CoroutineType)
                    self.assertEqual(create_task_arg.__qualname__, self.cog.sync.__qualname__)
                    create_task_arg.close()

    async def test_sync_cog_sync_guild(self):
        """Roles and users should be synced only if a guild is successfully retrieved."""
        guild = helpers.MockGuild()
        self.bot.reset_mock()
        self.RoleSyncer.reset_mock()
        self.UserSyncer.reset_mock()

        self.bot.get_guild = mock.MagicMock(return_value=guild)
        await self.cog.cog_load()

        with mock.patch("asyncio.sleep", new_callable=unittest.mock.AsyncMock):
            await self.cog.sync()

        self.bot.wait_until_guild_available.assert_called_once()
        self.bot.get_guild.assert_called_once_with(constants.Guild.id)

        self.RoleSyncer.sync.assert_called_once()
        self.UserSyncer.sync.assert_called_once()

    async def patch_user_helper(self, side_effect: BaseException) -> None:
        """Helper to set a side effect for bot.api_client.patch and then assert it is called."""
        self.bot.api_client.patch.reset_mock(side_effect=True)
        self.bot.api_client.patch.side_effect = side_effect

        user_id, updated_information = 5, {"key": 123}
        await self.cog.patch_user(user_id, updated_information)

        self.bot.api_client.patch.assert_called_once_with(
            f"bot/users/{user_id}",
            json=updated_information,
        )

    async def test_sync_cog_patch_user(self):
        """A PATCH request should be sent and 404 errors ignored."""
        for side_effect in (None, self.response_error(404)):
            with self.subTest(side_effect=side_effect):
                await self.patch_user_helper(side_effect)

    async def test_sync_cog_patch_user_non_404(self):
        """A PATCH request should be sent and the error raised if it's not a 404."""
        with self.assertRaises(ResponseCodeError):
            await self.patch_user_helper(self.response_error(500))


class SyncCogListenerTests(SyncCogTestCase):
    """Tests for the listeners of the Sync cog."""

    def setUp(self):
        super().setUp()
        self.cog.patch_user = mock.AsyncMock(spec_set=self.cog.patch_user)

        self.guild_id_patcher = mock.patch("bot.exts.backend.sync._cog.constants.Guild.id", 5)
        self.guild_id = self.guild_id_patcher.start()

        self.guild = helpers.MockGuild(id=self.guild_id)
        self.other_guild = helpers.MockGuild(id=0)

    def tearDown(self):
        self.guild_id_patcher.stop()

    async def test_sync_cog_on_guild_role_create(self):
        """A POST request should be sent with the new role's data."""
        self.assertTrue(self.cog.on_guild_role_create.__cog_listener__)

        role_data = {
            "colour": 49,
            "id": 777,
            "name": "rolename",
            "permissions": 8,
            "position": 23,
        }
        role = helpers.MockRole(**role_data, guild=self.guild)
        await self.cog.on_guild_role_create(role)

        self.bot.api_client.post.assert_called_once_with("bot/roles", json=role_data)

    async def test_sync_cog_on_guild_role_create_ignores_guilds(self):
        """Events from other guilds should be ignored."""
        role = helpers.MockRole(guild=self.other_guild)
        await self.cog.on_guild_role_create(role)
        self.bot.api_client.post.assert_not_awaited()

    async def test_sync_cog_on_guild_role_delete(self):
        """A DELETE request should be sent."""
        self.assertTrue(self.cog.on_guild_role_delete.__cog_listener__)

        role = helpers.MockRole(id=99, guild=self.guild)
        await self.cog.on_guild_role_delete(role)

        self.bot.api_client.delete.assert_called_once_with("bot/roles/99")

    async def test_sync_cog_on_guild_role_delete_ignores_guilds(self):
        """Events from other guilds should be ignored."""
        role = helpers.MockRole(guild=self.other_guild)
        await self.cog.on_guild_role_delete(role)
        self.bot.api_client.delete.assert_not_awaited()

    async def test_sync_cog_on_guild_role_update(self):
        """A PUT request should be sent if the colour, name, permissions, or position changes."""
        self.assertTrue(self.cog.on_guild_role_update.__cog_listener__)

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

                    before_role = helpers.MockRole(**role_data, guild=self.guild)
                    after_role = helpers.MockRole(**after_role_data, guild=self.guild)

                    await self.cog.on_guild_role_update(before_role, after_role)

                    if should_put:
                        self.bot.api_client.put.assert_called_once_with(
                            f"bot/roles/{after_role.id}",
                            json=after_role_data
                        )
                    else:
                        self.bot.api_client.put.assert_not_called()

    async def test_sync_cog_on_guild_role_update_ignores_guilds(self):
        """Events from other guilds should be ignored."""
        role = helpers.MockRole(guild=self.other_guild)
        await self.cog.on_guild_role_update(role, role)
        self.bot.api_client.put.assert_not_awaited()

    async def test_sync_cog_on_member_remove(self):
        """Member should be patched to set in_guild as False."""
        self.assertTrue(self.cog.on_member_remove.__cog_listener__)

        member = helpers.MockMember(guild=self.guild)
        await self.cog.on_member_remove(member)

        self.cog.patch_user.assert_called_once_with(
            member.id,
            json={"in_guild": False}
        )

    async def test_sync_cog_on_member_remove_ignores_guilds(self):
        """Events from other guilds should be ignored."""
        member = helpers.MockMember(guild=self.other_guild)
        await self.cog.on_member_remove(member)
        self.cog.patch_user.assert_not_awaited()

    async def test_sync_cog_on_member_update_roles(self):
        """Members should be patched if their roles have changed."""
        self.assertTrue(self.cog.on_member_update.__cog_listener__)

        # Roles are intentionally unsorted.
        before_roles = [helpers.MockRole(id=12), helpers.MockRole(id=30), helpers.MockRole(id=20)]
        before_member = helpers.MockMember(roles=before_roles, guild=self.guild)
        after_member = helpers.MockMember(roles=before_roles[1:], guild=self.guild)

        await self.cog.on_member_update(before_member, after_member)

        data = {"roles": sorted(role.id for role in after_member.roles)}
        self.cog.patch_user.assert_called_once_with(after_member.id, json=data)

    async def test_sync_cog_on_member_update_other(self):
        """Members should not be patched if other attributes have changed."""
        self.assertTrue(self.cog.on_member_update.__cog_listener__)

        subtests = (
            ("activities", discord.Game("Pong"), discord.Game("Frogger")),
            ("nick", "old nick", "new nick"),
            ("status", discord.Status.online, discord.Status.offline),
        )

        for attribute, old_value, new_value in subtests:
            with self.subTest(attribute=attribute):
                self.cog.patch_user.reset_mock()

                before_member = helpers.MockMember(**{attribute: old_value}, guild=self.guild)
                after_member = helpers.MockMember(**{attribute: new_value}, guild=self.guild)

                await self.cog.on_member_update(before_member, after_member)

                self.cog.patch_user.assert_not_called()

    async def test_sync_cog_on_member_update_ignores_guilds(self):
        """Events from other guilds should be ignored."""
        member = helpers.MockMember(guild=self.other_guild)
        await self.cog.on_member_update(member, member)
        self.cog.patch_user.assert_not_awaited()

    async def test_sync_cog_on_user_update(self):
        """A user should be patched only if the name, discriminator, or avatar changes."""
        self.assertTrue(self.cog.on_user_update.__cog_listener__)

        before_data = {
            "name": "old name",
            "discriminator": "1234",
            "bot": False,
        }

        subtests = (
            (True, "name", "name", "new name", "new name"),
            (True, "discriminator", "discriminator", "8765", 8765),
            (False, "bot", "bot", True, True),
        )

        for should_patch, attribute, api_field, value, api_value in subtests:
            with self.subTest(attribute=attribute):
                self.cog.patch_user.reset_mock()

                after_data = before_data.copy()
                after_data[attribute] = value
                before_user = helpers.MockUser(**before_data)
                after_user = helpers.MockUser(**after_data)

                await self.cog.on_user_update(before_user, after_user)

                if should_patch:
                    self.cog.patch_user.assert_called_once()

                    # Don't care if *all* keys are present; only the changed one is required
                    call_args = self.cog.patch_user.call_args
                    self.assertEqual(call_args.args[0], after_user.id)
                    self.assertIn("json", call_args.kwargs)

                    self.assertIn("ignore_404", call_args.kwargs)
                    self.assertTrue(call_args.kwargs["ignore_404"])

                    json = call_args.kwargs["json"]
                    self.assertIn(api_field, json)
                    self.assertEqual(json[api_field], api_value)
                else:
                    self.cog.patch_user.assert_not_called()

    async def on_member_join_helper(self, side_effect: Exception) -> dict:
        """
        Helper to set `side_effect` for on_member_join and assert a PUT request was sent.

        The request data for the mock member is returned. All exceptions will be re-raised.
        """
        member = helpers.MockMember(
            discriminator="1234",
            roles=[helpers.MockRole(id=22), helpers.MockRole(id=12)],
            guild=self.guild,
        )

        data = {
            "discriminator": int(member.discriminator),
            "id": member.id,
            "in_guild": True,
            "name": member.name,
            "roles": sorted(role.id for role in member.roles)
        }

        self.bot.api_client.put.reset_mock(side_effect=True)
        self.bot.api_client.put.side_effect = side_effect

        try:
            await self.cog.on_member_join(member)
        except Exception:
            raise
        finally:
            self.bot.api_client.put.assert_called_once_with(
                f"bot/users/{member.id}",
                json=data
            )

        return data

    async def test_sync_cog_on_member_join(self):
        """Should PUT user's data or POST it if the user doesn't exist."""
        for side_effect in (None, self.response_error(404)):
            with self.subTest(side_effect=side_effect):
                self.bot.api_client.post.reset_mock()
                data = await self.on_member_join_helper(side_effect)

                if side_effect:
                    self.bot.api_client.post.assert_called_once_with("bot/users", json=data)
                else:
                    self.bot.api_client.post.assert_not_called()

    async def test_sync_cog_on_member_join_non_404(self):
        """ResponseCodeError should be re-raised if status code isn't a 404."""
        with self.assertRaises(ResponseCodeError):
            await self.on_member_join_helper(self.response_error(500))

        self.bot.api_client.post.assert_not_called()

    async def test_sync_cog_on_member_join_ignores_guilds(self):
        """Events from other guilds should be ignored."""
        member = helpers.MockMember(guild=self.other_guild)
        await self.cog.on_member_join(member)
        self.bot.api_client.post.assert_not_awaited()
        self.bot.api_client.put.assert_not_awaited()


class SyncCogCommandTests(SyncCogTestCase, CommandTestCase):
    """Tests for the commands in the Sync cog."""

    async def test_sync_roles_command(self):
        """sync() should be called on the RoleSyncer."""
        ctx = helpers.MockContext()
        await self.cog.sync_roles_command(self.cog, ctx)

        self.RoleSyncer.sync.assert_called_once_with(ctx.guild, ctx)

    async def test_sync_users_command(self):
        """sync() should be called on the UserSyncer."""
        ctx = helpers.MockContext()
        await self.cog.sync_users_command(self.cog, ctx)

        self.UserSyncer.sync.assert_called_once_with(ctx.guild, ctx)

    async def test_commands_require_admin(self):
        """The sync commands should only run if the author has the administrator permission."""
        cmds = (
            self.cog.sync_group,
            self.cog.sync_roles_command,
            self.cog.sync_users_command,
        )

        for cmd in cmds:
            with self.subTest(cmd=cmd):
                await self.assertHasPermissionsCheck(cmd, {"administrator": True})
