from bot.cogs.sync.syncers import get_roles_for_sync, Role


def test_get_roles_for_sync_empty_return_for_equal_roles():
    api_roles = {Role(id=41, name='name', colour=33, permissions=0x8)}
    guild_roles = {Role(id=41, name='name', colour=33, permissions=0x8)}

    assert get_roles_for_sync(guild_roles, api_roles) == (set(), set())


def test_get_roles_for_sync_returns_roles_to_update_with_non_id_diff():
    api_roles = {Role(id=41, name='old name', colour=35, permissions=0x8)}
    guild_roles = {Role(id=41, name='new name', colour=33, permissions=0x8)}

    assert get_roles_for_sync(guild_roles, api_roles) == (
        set(),
        guild_roles
    )


def test_get_roles_only_returns_roles_that_require_update():
    api_roles = {
        Role(id=41, name='old name', colour=33, permissions=0x8),
        Role(id=53, name='other role', colour=55, permissions=0)
    }
    guild_roles = {
        Role(id=41, name='new name', colour=35, permissions=0x8),
        Role(id=53, name='other role', colour=55, permissions=0)
    }

    assert get_roles_for_sync(guild_roles, api_roles) == (
        set(),
        {Role(id=41, name='new name', colour=35, permissions=0x8)},
    )


def test_get_roles_returns_new_roles_in_first_tuple_element():
    api_roles = {
        Role(id=41, name='name', colour=35, permissions=0x8),
    }
    guild_roles = {
        Role(id=41, name='name', colour=35, permissions=0x8),
        Role(id=53, name='other role', colour=55, permissions=0)
    }

    assert get_roles_for_sync(guild_roles, api_roles) == (
        {Role(id=53, name='other role', colour=55, permissions=0)},
        set()
    )


def test_get_roles_returns_roles_to_update_and_new_roles():
    api_roles = {
        Role(id=41, name='old name', colour=35, permissions=0x8),
    }
    guild_roles = {
        Role(id=41, name='new name', colour=40, permissions=0x16),
        Role(id=53, name='other role', colour=55, permissions=0)
    }

    assert get_roles_for_sync(guild_roles, api_roles) == (
        {Role(id=53, name='other role', colour=55, permissions=0)},
        {Role(id=41, name='new name', colour=40, permissions=0x16)}
    )
