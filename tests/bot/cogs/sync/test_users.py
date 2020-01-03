import asyncio
import unittest

from bot.cogs.sync.syncers import UserSyncer
from tests import helpers


def fake_user(**kwargs):
    """Fixture to return a dictionary representing a user with default values set."""
    kwargs.setdefault("id", 43)
    kwargs.setdefault("name", "bob the test man")
    kwargs.setdefault("discriminator", 1337)
    kwargs.setdefault("avatar_hash", None)
    kwargs.setdefault("roles", (666,))
    kwargs.setdefault("in_guild", True)

    return kwargs


class UserSyncerDiffTests(unittest.TestCase):
    """Tests for determining differences between users in the DB and users in the Guild cache."""

    def setUp(self):
        self.bot = helpers.MockBot()
        self.syncer = UserSyncer(self.bot)

    @staticmethod
    def get_guild(*members):
        """Fixture to return a guild object with the given members."""
        guild = helpers.MockGuild()
        guild.members = []

        for member in members:
            member = member.copy()
            member["avatar"] = member.pop("avatar_hash")
            del member["in_guild"]

            mock_member = helpers.MockMember(**member)
            mock_member.roles = [helpers.MockRole(id=role_id) for role_id in member["roles"]]

            guild.members.append(mock_member)

        return guild

    def test_empty_diff_for_no_users(self):
        """When no users are given, an empty diff should be returned."""
        guild = self.get_guild()

        actual_diff = asyncio.run(self.syncer._get_diff(guild))
        expected_diff = (set(), set(), None)

        self.assertEqual(actual_diff, expected_diff)

    def test_empty_diff_for_identical_users(self):
        """No differences should be found if the users in the guild and DB are identical."""
        self.bot.api_client.get.return_value = [fake_user()]
        guild = self.get_guild(fake_user())

        actual_diff = asyncio.run(self.syncer._get_diff(guild))
        expected_diff = (set(), set(), None)

        self.assertEqual(actual_diff, expected_diff)

    def test_get_users_for_sync_returns_users_to_update_on_non_id_field_diff(self):
        """When a non-ID-field differs, the user to update is returned."""
        api_users = {43: fake_user()}
        guild_users = {43: fake_user(name='new fancy name')}

        self.assertEqual(
            get_users_for_sync(guild_users, api_users),
            (set(), {fake_user(name='new fancy name')})
        )

    def test_get_users_for_sync_returns_users_to_create_with_new_ids_on_guild(self):
        """When new users join the guild, they are returned as the first tuple element."""
        api_users = {43: fake_user()}
        guild_users = {43: fake_user(), 63: fake_user(id=63)}

        self.assertEqual(
            get_users_for_sync(guild_users, api_users),
            ({fake_user(id=63)}, set())
        )

    def test_get_users_for_sync_updates_in_guild_field_on_user_leave(self):
        """When a user leaves the guild, the `in_guild` flag is updated to `False`."""
        api_users = {43: fake_user(), 63: fake_user(id=63)}
        guild_users = {43: fake_user()}

        self.assertEqual(
            get_users_for_sync(guild_users, api_users),
            (set(), {fake_user(id=63, in_guild=False)})
        )

    def test_get_users_for_sync_updates_and_creates_users_as_needed(self):
        """When one user left and another one was updated, both are returned."""
        api_users = {43: fake_user()}
        guild_users = {63: fake_user(id=63)}

        self.assertEqual(
            get_users_for_sync(guild_users, api_users),
            ({fake_user(id=63)}, {fake_user(in_guild=False)})
        )

    def test_get_users_for_sync_does_not_duplicate_update_users(self):
        """When the API knows a user the guild doesn't, nothing is performed."""
        api_users = {43: fake_user(in_guild=False)}
        guild_users = {}

        self.assertEqual(
            get_users_for_sync(guild_users, api_users),
            (set(), set())
        )
