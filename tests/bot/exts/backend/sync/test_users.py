import unittest

from bot.exts.backend.sync._syncers import UserSyncer, _Diff
from tests import helpers


def fake_user(**kwargs):
    """Fixture to return a dictionary representing a user with default values set."""
    kwargs.setdefault("id", 43)
    kwargs.setdefault("name", "bob the test man")
    kwargs.setdefault("discriminator", 1337)
    kwargs.setdefault("roles", [666])
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

    @staticmethod
    def get_mock_member(member: dict):
        member = member.copy()
        del member["in_guild"]
        mock_member = helpers.MockMember(**member)
        mock_member.roles = [helpers.MockRole(id=role_id) for role_id in member["roles"]]
        return mock_member

    async def test_empty_diff_for_no_users(self):
        """When no users are given, an empty diff should be returned."""
        self.bot.api_client.get.return_value = {
            "count": 3,
            "next_page_no": None,
            "previous_page_no": None,
            "results": []
        }
        guild = self.get_guild()

        actual_diff = await self.syncer._get_diff(guild)
        expected_diff = ([], [], None)

        self.assertEqual(actual_diff, expected_diff)

    async def test_empty_diff_for_identical_users(self):
        """No differences should be found if the users in the guild and DB are identical."""
        self.bot.api_client.get.return_value = {
            "count": 3,
            "next_page_no": None,
            "previous_page_no": None,
            "results": [fake_user()]
        }
        guild = self.get_guild(fake_user())

        guild.get_member.return_value = self.get_mock_member(fake_user())
        actual_diff = await self.syncer._get_diff(guild)
        expected_diff = ([], [], None)

        self.assertEqual(actual_diff, expected_diff)

    async def test_diff_for_updated_users(self):
        """Only updated users should be added to the 'updated' set of the diff."""
        updated_user = fake_user(id=99, name="new")

        self.bot.api_client.get.return_value = {
            "count": 3,
            "next_page_no": None,
            "previous_page_no": None,
            "results": [fake_user(id=99, name="old"), fake_user()]
        }
        guild = self.get_guild(updated_user, fake_user())
        guild.get_member.side_effect = [
            self.get_mock_member(updated_user),
            self.get_mock_member(fake_user())
        ]

        actual_diff = await self.syncer._get_diff(guild)
        expected_diff = ([], [{"id": 99, "name": "new"}], None)

        self.assertEqual(actual_diff, expected_diff)

    async def test_diff_for_new_users(self):
        """Only new users should be added to the 'created' list of the diff."""
        new_user = fake_user(id=99, name="new")

        self.bot.api_client.get.return_value = {
            "count": 3,
            "next_page_no": None,
            "previous_page_no": None,
            "results": [fake_user()]
        }
        guild = self.get_guild(fake_user(), new_user)
        guild.get_member.side_effect = [
            self.get_mock_member(fake_user()),
            self.get_mock_member(new_user)
        ]
        actual_diff = await self.syncer._get_diff(guild)
        expected_diff = ([new_user], [], None)

        self.assertEqual(actual_diff, expected_diff)

    async def test_diff_sets_in_guild_false_for_leaving_users(self):
        """When a user leaves the guild, the `in_guild` flag is updated to `False`."""
        self.bot.api_client.get.return_value = {
            "count": 3,
            "next_page_no": None,
            "previous_page_no": None,
            "results": [fake_user(), fake_user(id=63)]
        }
        guild = self.get_guild(fake_user())
        guild.get_member.side_effect = [
            self.get_mock_member(fake_user()),
            None
        ]

        actual_diff = await self.syncer._get_diff(guild)
        expected_diff = ([], [{"id": 63, "in_guild": False}], None)

        self.assertEqual(actual_diff, expected_diff)

    async def test_diff_for_new_updated_and_leaving_users(self):
        """When users are added, updated, and removed, all of them are returned properly."""
        new_user = fake_user(id=99, name="new")

        updated_user = fake_user(id=55, name="updated")

        self.bot.api_client.get.return_value = {
            "count": 3,
            "next_page_no": None,
            "previous_page_no": None,
            "results": [fake_user(), fake_user(id=55), fake_user(id=63)]
        }
        guild = self.get_guild(fake_user(), new_user, updated_user)
        guild.get_member.side_effect = [
            self.get_mock_member(fake_user()),
            self.get_mock_member(updated_user),
            None
        ]

        actual_diff = await self.syncer._get_diff(guild)
        expected_diff = ([new_user], [{"id": 55, "name": "updated"}, {"id": 63, "in_guild": False}], None)

        self.assertEqual(actual_diff, expected_diff)

    async def test_empty_diff_for_db_users_not_in_guild(self):
        """When the DB knows a user, but the guild doesn't, no difference is found."""
        self.bot.api_client.get.return_value = {
            "count": 3,
            "next_page_no": None,
            "previous_page_no": None,
            "results": [fake_user(), fake_user(id=63, in_guild=False)]
        }
        guild = self.get_guild(fake_user())
        guild.get_member.side_effect = [
            self.get_mock_member(fake_user()),
            None
        ]

        actual_diff = await self.syncer._get_diff(guild)
        expected_diff = ([], [], None)

        self.assertEqual(actual_diff, expected_diff)


class UserSyncerSyncTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the API requests that sync users."""

    def setUp(self):
        self.bot = helpers.MockBot()
        self.syncer = UserSyncer(self.bot)

    async def test_sync_created_users(self):
        """Only POST requests should be made with the correct payload."""
        users = [fake_user(id=111), fake_user(id=222)]

        diff = _Diff(users, [], None)
        await self.syncer._sync(diff)

        self.bot.api_client.post.assert_called_once_with("bot/users", json=diff.created)

        self.bot.api_client.put.assert_not_called()
        self.bot.api_client.delete.assert_not_called()

    async def test_sync_updated_users(self):
        """Only PUT requests should be made with the correct payload."""
        users = [fake_user(id=111), fake_user(id=222)]

        diff = _Diff([], users, None)
        await self.syncer._sync(diff)

        self.bot.api_client.patch.assert_called_once_with("bot/users/bulk_patch", json=diff.updated)

        self.bot.api_client.post.assert_not_called()
        self.bot.api_client.delete.assert_not_called()
