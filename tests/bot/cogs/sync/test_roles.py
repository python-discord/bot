import asyncio
import unittest

import discord

from bot.cogs.sync.syncers import RoleSyncer, _Role
from tests import helpers


class RoleSyncerDiffTests(unittest.TestCase):
    """Tests for determining differences between roles in the DB and roles in the Guild cache."""

    def setUp(self):
        self.bot = helpers.MockBot()
        self.syncer = RoleSyncer(self.bot)
        self.constant_role = {"id": 9, "name": "test", "colour": 7, "permissions": 0, "position": 3}

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

    def test_empty_diff_for_identical_roles(self):
        """No differences should be found if the roles in the guild and DB are identical."""
        self.bot.api_client.get.return_value = [self.constant_role]
        guild = self.get_guild(self.constant_role)

        actual_diff = asyncio.run(self.syncer._get_diff(guild))
        expected_diff = (set(), set(), set())

        self.assertEqual(actual_diff, expected_diff)

    def test_diff_for_updated_roles(self):
        """Only updated roles should be added to the 'updated' set of the diff."""
        updated_role = {"id": 41, "name": "new", "colour": 33, "permissions": 0x8, "position": 1}

        self.bot.api_client.get.return_value = [
            {"id": 41, "name": "old", "colour": 33, "permissions": 0x8, "position": 1},
            self.constant_role,
        ]
        guild = self.get_guild(updated_role, self.constant_role)

        actual_diff = asyncio.run(self.syncer._get_diff(guild))
        expected_diff = (set(), {_Role(**updated_role)}, set())

        self.assertEqual(actual_diff, expected_diff)

    def test_diff_for_new_roles(self):
        """Only new roles should be added to the 'created' set of the diff."""
        new_role = {"id": 41, "name": "new", "colour": 33, "permissions": 0x8, "position": 1}

        self.bot.api_client.get.return_value = [self.constant_role]
        guild = self.get_guild(self.constant_role, new_role)

        actual_diff = asyncio.run(self.syncer._get_diff(guild))
        expected_diff = ({_Role(**new_role)}, set(), set())

        self.assertEqual(actual_diff, expected_diff)

    def test_diff_for_deleted_roles(self):
        """Only deleted roles should be added to the 'deleted' set of the diff."""
        deleted_role = {"id": 61, "name": "delete", "colour": 99, "permissions": 0x9, "position": 2}

        self.bot.api_client.get.return_value = [self.constant_role, deleted_role]
        guild = self.get_guild(self.constant_role)

        actual_diff = asyncio.run(self.syncer._get_diff(guild))
        expected_diff = (set(), set(), {_Role(**deleted_role)})

        self.assertEqual(actual_diff, expected_diff)

    def test_diff_for_new_updated_and_deleted_roles(self):
        """When roles are added, updated, and removed, all of them are returned properly."""
        new = {"id": 41, "name": "new", "colour": 33, "permissions": 0x8, "position": 1}
        updated = {"id": 71, "name": "updated", "colour": 101, "permissions": 0x5, "position": 4}
        deleted = {"id": 61, "name": "delete", "colour": 99, "permissions": 0x9, "position": 2}

        self.bot.api_client.get.return_value = [
            self.constant_role,
            {"id": 71, "name": "update", "colour": 99, "permissions": 0x9, "position": 4},
            deleted,
        ]
        guild = self.get_guild(self.constant_role, new, updated)

        actual_diff = asyncio.run(self.syncer._get_diff(guild))
        expected_diff = ({_Role(**new)}, {_Role(**updated)}, {_Role(**deleted)})

        self.assertEqual(actual_diff, expected_diff)


class RoleSyncerSyncTests(unittest.TestCase):
    """Tests for the API requests that sync roles."""

    def setUp(self):
        self.bot = helpers.MockBot()
        self.syncer = RoleSyncer(self.bot)
