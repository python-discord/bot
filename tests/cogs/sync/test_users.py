from bot.cogs.sync.syncers import User, get_users_for_sync

def fake_user(**kwargs):
    kwargs.setdefault('id', 43)
    kwargs.setdefault('name', 'bob the test man')
    kwargs.setdefault('discriminator', 1337)
    kwargs.setdefault('avatar_hash', None)
    kwargs.setdefault('roles', (666,))
    kwargs.setdefault('in_guild', True)
    return User(**kwargs)


def test_get_users_for_sync_returns_nothing_for_empty_params():
    assert get_users_for_sync({}, {}) == (set(), set())


def test_get_users_for_sync_returns_nothing_for_equal_users():
    api_users = {43: fake_user()}
    guild_users = {43: fake_user()}

    assert get_users_for_sync(guild_users, api_users) == (set(), set())


def test_get_users_for_sync_returns_users_to_update_on_non_id_field_diff():
    api_users = {43: fake_user()}
    guild_users = {43: fake_user(name='new fancy name')}

    assert get_users_for_sync(guild_users, api_users) == (
        set(),
        {fake_user(name='new fancy name')}
    )


def test_get_users_for_sync_returns_users_to_create_with_new_ids_on_guild():
    api_users = {43: fake_user()}
    guild_users = {43: fake_user(), 63: fake_user(id=63)}

    assert get_users_for_sync(guild_users, api_users) == (
        {fake_user(id=63)},
        set()
    )


def test_get_users_for_sync_updates_in_guild_field_on_user_leave():
    api_users = {43: fake_user(), 63: fake_user(id=63)}
    guild_users = {43: fake_user()}

    assert get_users_for_sync(guild_users, api_users) == (
        set(),
        {fake_user(id=63, in_guild=False)}
    )


def test_get_users_for_sync_updates_and_creates_users_as_needed():
    api_users = {43: fake_user()}
    guild_users = {63: fake_user(id=63)}

    assert get_users_for_sync(guild_users, api_users) == (
        {fake_user(id=63)},
        {fake_user(in_guild=False)}
    )


def test_get_users_for_sync_does_not_duplicate_update_users():
    api_users = {43: fake_user(in_guild=False)}
    guild_users = {}

    assert get_users_for_sync(guild_users, api_users) == (set(), set())
