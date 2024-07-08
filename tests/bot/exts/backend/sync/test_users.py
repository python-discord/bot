import unittest
from unittest import mock

from discord.errors import NotFound

from bot.exts.backend.sync._syncers import UserSyncer, _Diff
from tests import helpers


def fake_user(**kwargs):
    """Fixture to return a dictionary representing a user with default values set."""
    kwargs.setdefault("id", 43)
    kwargs.setdefault("name", "bob the test man")
    kwargs.setdefault("display_name", "bob")
    kwargs.setdefault("discriminator", 1337)
    kwargs.setdefault("roles", [helpers.MockRole(id=666)])
    kwargs.setdefault("in_guild", True)

    return kwargs


class UserSyncerDiffTests(unittest.IsolatedAsyncioTestCase):
    """Tests for determining differences between users in the DB and users in the Guild cache."""

    def setUp(self):
        patcher = mock.patch("bot.instance", new=helpers.MockBot())
        self.bot = patcher.start()
        self.addCleanup(patcher.stop)

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

        actual_diff = await UserSyncer._get_diff(guild)
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
        actual_diff = await UserSyncer._get_diff(guild)
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

        actual_diff = await UserSyncer._get_diff(guild)
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
        actual_diff = await UserSyncer._get_diff(guild)
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
        guild.fetch_member.side_effect = NotFound(mock.Mock(status=404), "Not found")

        actual_diff = await UserSyncer._get_diff(guild)
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
        guild.fetch_member.side_effect = NotFound(mock.Mock(status=404), "Not found")

        actual_diff = await UserSyncer._get_diff(guild)
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
        guild.fetch_member.side_effect = NotFound(mock.Mock(status=404), "Not found")

        actual_diff = await UserSyncer._get_diff(guild)
        expected_diff = ([], [], None)

        self.assertEqual(actual_diff, expected_diff)


class UserSyncerSyncTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the API requests that sync users."""

    def setUp(self):
        bot_patcher = mock.patch("bot.instance", new=helpers.MockBot())
        self.bot = bot_patcher.start()
        self.addCleanup(bot_patcher.stop)

        chunk_patcher = mock.patch("bot.exts.backend.sync._syncers.CHUNK_SIZE", 2)
        self.chunk_size = chunk_patcher.start()
        self.addCleanup(chunk_patcher.stop)

        self.chunk_count = 2
        self.users = [fake_user(id=i) for i in range(self.chunk_size * self.chunk_count)]

    async def test_sync_created_users(self):
        """Only POST requests should be made with the correct payload."""
        diff = _Diff(self.users, [], None)
        await UserSyncer._sync(diff)

        self.bot.api_client.post.assert_any_call("bot/users", json=tuple(diff.created[:self.chunk_size]))
        self.bot.api_client.post.assert_any_call("bot/users", json=tuple(diff.created[self.chunk_size:]))
        self.assertEqual(self.bot.api_client.post.call_count, self.chunk_count)

        self.bot.api_client.put.assert_not_called()
        self.bot.api_client.delete.assert_not_called()

    async def test_sync_updated_users(self):
        """Only PUT requests should be made with the correct payload."""
        diff = _Diff([], self.users, None)
        await UserSyncer._sync(diff)

        self.bot.api_client.patch.assert_any_call("bot/users/bulk_patch", json=tuple(diff.updated[:self.chunk_size]))
        self.bot.api_client.patch.assert_any_call("bot/users/bulk_patch", json=tuple(diff.updated[self.chunk_size:]))
        self.assertEqual(self.bot.api_client.patch.call_count, self.chunk_count)

        self.bot.api_client.post.assert_not_called()
        self.bot.api_client.delete.assert_not_called()
