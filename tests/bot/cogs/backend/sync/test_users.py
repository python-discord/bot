import unittest
from unittest import mock

from bot.cogs.backend.sync._syncers import UserSyncer, _Diff, _User
from tests import helpers


def fake_user(**kwargs):
    """Fixture to return a dictionary representing a user with default values set."""
    kwargs.setdefault("id", 43)
    kwargs.setdefault("name", "bob the test man")
    kwargs.setdefault("discriminator", 1337)
    kwargs.setdefault("roles", (666,))
    kwargs.setdefault("in_guild", True)

    return kwargs


class UserSyncerDiffTests(unittest.IsolatedAsyncioTestCase):
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
            del member["in_guild"]

            mock_member = helpers.MockMember(**member)
            mock_member.roles = [helpers.MockRole(id=role_id) for role_id in member["roles"]]

            guild.members.append(mock_member)

        return guild

    async def test_empty_diff_for_no_users(self):
        """When no users are given, an empty diff should be returned."""
        guild = self.get_guild()

        actual_diff = await self.syncer._get_diff(guild)
        expected_diff = (set(), set(), None)

        self.assertEqual(actual_diff, expected_diff)

    async def test_empty_diff_for_identical_users(self):
        """No differences should be found if the users in the guild and DB are identical."""
        self.bot.api_client.get.return_value = [fake_user()]
        guild = self.get_guild(fake_user())

        actual_diff = await self.syncer._get_diff(guild)
        expected_diff = (set(), set(), None)

        self.assertEqual(actual_diff, expected_diff)

    async def test_diff_for_updated_users(self):
        """Only updated users should be added to the 'updated' set of the diff."""
        updated_user = fake_user(id=99, name="new")

        self.bot.api_client.get.return_value = [fake_user(id=99, name="old"), fake_user()]
        guild = self.get_guild(updated_user, fake_user())

        actual_diff = await self.syncer._get_diff(guild)
        expected_diff = (set(), {_User(**updated_user)}, None)

        self.assertEqual(actual_diff, expected_diff)

    async def test_diff_for_new_users(self):
        """Only new users should be added to the 'created' set of the diff."""
        new_user = fake_user(id=99, name="new")

        self.bot.api_client.get.return_value = [fake_user()]
        guild = self.get_guild(fake_user(), new_user)

        actual_diff = await self.syncer._get_diff(guild)
        expected_diff = ({_User(**new_user)}, set(), None)

        self.assertEqual(actual_diff, expected_diff)

    async def test_diff_sets_in_guild_false_for_leaving_users(self):
        """When a user leaves the guild, the `in_guild` flag is updated to `False`."""
        leaving_user = fake_user(id=63, in_guild=False)

        self.bot.api_client.get.return_value = [fake_user(), fake_user(id=63)]
        guild = self.get_guild(fake_user())

        actual_diff = await self.syncer._get_diff(guild)
        expected_diff = (set(), {_User(**leaving_user)}, None)

        self.assertEqual(actual_diff, expected_diff)

    async def test_diff_for_new_updated_and_leaving_users(self):
        """When users are added, updated, and removed, all of them are returned properly."""
        new_user = fake_user(id=99, name="new")
        updated_user = fake_user(id=55, name="updated")
        leaving_user = fake_user(id=63, in_guild=False)

        self.bot.api_client.get.return_value = [fake_user(), fake_user(id=55), fake_user(id=63)]
        guild = self.get_guild(fake_user(), new_user, updated_user)

        actual_diff = await self.syncer._get_diff(guild)
        expected_diff = ({_User(**new_user)}, {_User(**updated_user), _User(**leaving_user)}, None)

        self.assertEqual(actual_diff, expected_diff)

    async def test_empty_diff_for_db_users_not_in_guild(self):
        """When the DB knows a user the guild doesn't, no difference is found."""
        self.bot.api_client.get.return_value = [fake_user(), fake_user(id=63, in_guild=False)]
        guild = self.get_guild(fake_user())

        actual_diff = await self.syncer._get_diff(guild)
        expected_diff = (set(), set(), None)

        self.assertEqual(actual_diff, expected_diff)


class UserSyncerSyncTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the API requests that sync users."""

    def setUp(self):
        self.bot = helpers.MockBot()
        self.syncer = UserSyncer(self.bot)

    async def test_sync_created_users(self):
        """Only POST requests should be made with the correct payload."""
        users = [fake_user(id=111), fake_user(id=222)]

        user_tuples = {_User(**user) for user in users}
        diff = _Diff(user_tuples, set(), None)
        await self.syncer._sync(diff)

        calls = [mock.call("bot/users", json=user) for user in users]
        self.bot.api_client.post.assert_has_calls(calls, any_order=True)
        self.assertEqual(self.bot.api_client.post.call_count, len(users))

        self.bot.api_client.put.assert_not_called()
        self.bot.api_client.delete.assert_not_called()

    async def test_sync_updated_users(self):
        """Only PUT requests should be made with the correct payload."""
        users = [fake_user(id=111), fake_user(id=222)]

        user_tuples = {_User(**user) for user in users}
        diff = _Diff(set(), user_tuples, None)
        await self.syncer._sync(diff)

        calls = [mock.call(f"bot/users/{user['id']}", json=user) for user in users]
        self.bot.api_client.put.assert_has_calls(calls, any_order=True)
        self.assertEqual(self.bot.api_client.put.call_count, len(users))

        self.bot.api_client.post.assert_not_called()
        self.bot.api_client.delete.assert_not_called()
