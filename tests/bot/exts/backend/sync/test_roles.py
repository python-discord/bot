import unittest
from unittest import mock

import discord

from bot.exts.backend.sync._syncers import RoleSyncer, _Diff, _Role
from tests import helpers


def fake_role(**kwargs):
    """Fixture to return a dictionary representing a role with default values set."""
    kwargs.setdefault("id", 9)
    kwargs.setdefault("name", "fake role")
    kwargs.setdefault("colour", 7)
    kwargs.setdefault("permissions", 0)
    kwargs.setdefault("position", 55)

    return kwargs


class RoleSyncerDiffTests(unittest.IsolatedAsyncioTestCase):
    """Tests for determining differences between roles in the DB and roles in the Guild cache."""

    def setUp(self):
        patcher = mock.patch("bot.instance", new=helpers.MockBot())
        self.bot = patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def get_guild(*roles):
        """Fixture to return a guild object with the given roles."""
        guild = helpers.MockGuild()
        guild.roles = []

        for role in roles:
            mock_role = helpers.MockRole(**role)
            mock_role.colour = discord.Colour(role["colour"])
            mock_role.permissions = discord.Permissions(role["permissions"])
            guild.roles.append(mock_role)

        return guild

    async def test_empty_diff_for_identical_roles(self):
        """No differences should be found if the roles in the guild and DB are identical."""
        self.bot.api_client.get.return_value = [fake_role()]
        guild = self.get_guild(fake_role())

        actual_diff = await RoleSyncer._get_diff(guild)
        expected_diff = (set(), set(), set())

        self.assertEqual(actual_diff, expected_diff)

    async def test_diff_for_updated_roles(self):
        """Only updated roles should be added to the 'updated' set of the diff."""
        updated_role = fake_role(id=41, name="new")

        self.bot.api_client.get.return_value = [fake_role(id=41, name="old"), fake_role()]
        guild = self.get_guild(updated_role, fake_role())

        actual_diff = await RoleSyncer._get_diff(guild)
        expected_diff = (set(), {_Role(**updated_role)}, set())

        self.assertEqual(actual_diff, expected_diff)

    async def test_diff_for_new_roles(self):
        """Only new roles should be added to the 'created' set of the diff."""
        new_role = fake_role(id=41, name="new")

        self.bot.api_client.get.return_value = [fake_role()]
        guild = self.get_guild(fake_role(), new_role)

        actual_diff = await RoleSyncer._get_diff(guild)
        expected_diff = ({_Role(**new_role)}, set(), set())

        self.assertEqual(actual_diff, expected_diff)

    async def test_diff_for_deleted_roles(self):
        """Only deleted roles should be added to the 'deleted' set of the diff."""
        deleted_role = fake_role(id=61, name="deleted")

        self.bot.api_client.get.return_value = [fake_role(), deleted_role]
        guild = self.get_guild(fake_role())

        actual_diff = await RoleSyncer._get_diff(guild)
        expected_diff = (set(), set(), {_Role(**deleted_role)})

        self.assertEqual(actual_diff, expected_diff)

    async def test_diff_for_new_updated_and_deleted_roles(self):
        """When roles are added, updated, and removed, all of them are returned properly."""
        new = fake_role(id=41, name="new")
        updated = fake_role(id=71, name="updated")
        deleted = fake_role(id=61, name="deleted")

        self.bot.api_client.get.return_value = [
            fake_role(),
            fake_role(id=71, name="updated name"),
            deleted,
        ]
        guild = self.get_guild(fake_role(), new, updated)

        actual_diff = await RoleSyncer._get_diff(guild)
        expected_diff = ({_Role(**new)}, {_Role(**updated)}, {_Role(**deleted)})

        self.assertEqual(actual_diff, expected_diff)


class RoleSyncerSyncTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the API requests that sync roles."""

    def setUp(self):
        patcher = mock.patch("bot.instance", new=helpers.MockBot())
        self.bot = patcher.start()
        self.addCleanup(patcher.stop)

    async def test_sync_created_roles(self):
        """Only POST requests should be made with the correct payload."""
        roles = [fake_role(id=111), fake_role(id=222)]

        role_tuples = {_Role(**role) for role in roles}
        diff = _Diff(role_tuples, set(), set())
        await RoleSyncer._sync(diff)

        calls = [mock.call("bot/roles", json=role) for role in roles]
        self.bot.api_client.post.assert_has_calls(calls, any_order=True)
        self.assertEqual(self.bot.api_client.post.call_count, len(roles))

        self.bot.api_client.put.assert_not_called()
        self.bot.api_client.delete.assert_not_called()

    async def test_sync_updated_roles(self):
        """Only PUT requests should be made with the correct payload."""
        roles = [fake_role(id=111), fake_role(id=222)]

        role_tuples = {_Role(**role) for role in roles}
        diff = _Diff(set(), role_tuples, set())
        await RoleSyncer._sync(diff)

        calls = [mock.call(f"bot/roles/{role['id']}", json=role) for role in roles]
        self.bot.api_client.put.assert_has_calls(calls, any_order=True)
        self.assertEqual(self.bot.api_client.put.call_count, len(roles))

        self.bot.api_client.post.assert_not_called()
        self.bot.api_client.delete.assert_not_called()

    async def test_sync_deleted_roles(self):
        """Only DELETE requests should be made with the correct payload."""
        roles = [fake_role(id=111), fake_role(id=222)]

        role_tuples = {_Role(**role) for role in roles}
        diff = _Diff(set(), set(), role_tuples)
        await RoleSyncer._sync(diff)

        calls = [mock.call(f"bot/roles/{role['id']}") for role in roles]
        self.bot.api_client.delete.assert_has_calls(calls, any_order=True)
        self.assertEqual(self.bot.api_client.delete.call_count, len(roles))

        self.bot.api_client.post.assert_not_called()
        self.bot.api_client.put.assert_not_called()
