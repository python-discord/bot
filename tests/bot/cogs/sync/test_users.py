import unittest

from bot.cogs.sync.syncers import User, get_users_for_sync


def fake_user(**kwargs):
    kwargs.setdefault('id', 43)
    kwargs.setdefault('name', 'bob the test man')
    kwargs.setdefault('discriminator', 1337)
    kwargs.setdefault('avatar_hash', None)
    kwargs.setdefault('roles', (666,))
    kwargs.setdefault('in_guild', True)
    return User(**kwargs)


class GetUsersForSyncTests(unittest.TestCase):
    """Tests constructing the users to synchronize with the site."""

    def test_get_users_for_sync_returns_nothing_for_empty_params(self):
        """When no users are given, none are returned."""
        self.assertEqual(
            get_users_for_sync({}, {}),
            (set(), set())
        )

    def test_get_users_for_sync_returns_nothing_for_equal_users(self):
        """When no users are updated, none are returned."""
        api_users = {43: fake_user()}
        guild_users = {43: fake_user()}

        self.assertEqual(
            get_users_for_sync(guild_users, api_users),
            (set(), set())
        )

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
