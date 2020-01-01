import asyncio
import unittest

import discord

from bot.cogs.sync.syncers import RoleSyncer
from tests import helpers


class RoleSyncerTests(unittest.TestCase):
    """Tests constructing the roles to synchronize with the site."""

    def setUp(self):
        self.bot = helpers.MockBot()
        self.syncer = RoleSyncer(self.bot)

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
        role = {"id": 41, "name": "name", "colour": 33, "permissions": 0x8, "position": 1}

        self.bot.api_client.get.return_value = [role]
        guild = self.get_guild(role)

        actual_diff = asyncio.run(self.syncer._get_diff(guild))
        expected_diff = (set(), set(), set())

        self.assertEqual(actual_diff, expected_diff)

    def test_get_roles_for_sync_returns_roles_to_update_with_non_id_diff(self):
        """Roles to be synced are returned when non-ID attributes differ."""
        api_roles = {Role(id=41, name='old name', colour=35, permissions=0x8, position=1)}
        guild_roles = {Role(id=41, name='new name', colour=33, permissions=0x8, position=2)}

        self.assertEqual(
            get_roles_for_sync(guild_roles, api_roles),
            (set(), guild_roles, set())
        )

    def test_get_roles_only_returns_roles_that_require_update(self):
        """Roles that require an update should be returned as the second tuple element."""
        api_roles = {
            Role(id=41, name='old name', colour=33, permissions=0x8, position=1),
            Role(id=53, name='other role', colour=55, permissions=0, position=3)
        }
        guild_roles = {
            Role(id=41, name='new name', colour=35, permissions=0x8, position=2),
            Role(id=53, name='other role', colour=55, permissions=0, position=3)
        }

        self.assertEqual(
            get_roles_for_sync(guild_roles, api_roles),
            (
                set(),
                {Role(id=41, name='new name', colour=35, permissions=0x8, position=2)},
                set(),
            )
        )

    def test_get_roles_returns_new_roles_in_first_tuple_element(self):
        """Newly created roles are returned as the first tuple element."""
        api_roles = {
            Role(id=41, name='name', colour=35, permissions=0x8, position=1),
        }
        guild_roles = {
            Role(id=41, name='name', colour=35, permissions=0x8, position=1),
            Role(id=53, name='other role', colour=55, permissions=0, position=2)
        }

        self.assertEqual(
            get_roles_for_sync(guild_roles, api_roles),
            (
                {Role(id=53, name='other role', colour=55, permissions=0, position=2)},
                set(),
                set(),
            )
        )

    def test_get_roles_returns_roles_to_update_and_new_roles(self):
        """Newly created and updated roles should be returned together."""
        api_roles = {
            Role(id=41, name='old name', colour=35, permissions=0x8, position=1),
        }
        guild_roles = {
            Role(id=41, name='new name', colour=40, permissions=0x16, position=2),
            Role(id=53, name='other role', colour=55, permissions=0, position=3)
        }

        self.assertEqual(
            get_roles_for_sync(guild_roles, api_roles),
            (
                {Role(id=53, name='other role', colour=55, permissions=0, position=3)},
                {Role(id=41, name='new name', colour=40, permissions=0x16, position=2)},
                set(),
            )
        )

    def test_get_roles_returns_roles_to_delete(self):
        """Roles to be deleted should be returned as the third tuple element."""
        api_roles = {
            Role(id=41, name='name', colour=35, permissions=0x8, position=1),
            Role(id=61, name='to delete', colour=99, permissions=0x9, position=2),
        }
        guild_roles = {
            Role(id=41, name='name', colour=35, permissions=0x8, position=1),
        }

        self.assertEqual(
            get_roles_for_sync(guild_roles, api_roles),
            (
                set(),
                set(),
                {Role(id=61, name='to delete', colour=99, permissions=0x9, position=2)},
            )
        )

    def test_get_roles_returns_roles_to_delete_update_and_new_roles(self):
        """When roles were added, updated, and removed, all of them are returned properly."""
        api_roles = {
            Role(id=41, name='not changed', colour=35, permissions=0x8, position=1),
            Role(id=61, name='to delete', colour=99, permissions=0x9, position=2),
            Role(id=71, name='to update', colour=99, permissions=0x9, position=3),
        }
        guild_roles = {
            Role(id=41, name='not changed', colour=35, permissions=0x8, position=1),
            Role(id=81, name='to create', colour=99, permissions=0x9, position=4),
            Role(id=71, name='updated', colour=101, permissions=0x5, position=3),
        }

        self.assertEqual(
            get_roles_for_sync(guild_roles, api_roles),
            (
                {Role(id=81, name='to create', colour=99, permissions=0x9, position=4)},
                {Role(id=71, name='updated', colour=101, permissions=0x5, position=3)},
                {Role(id=61, name='to delete', colour=99, permissions=0x9, position=2)},
            )
        )
