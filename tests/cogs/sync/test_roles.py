from bot.cogs.sync.syncers import Role, get_roles_for_sync


def test_get_roles_for_sync_empty_return_for_equal_roles():
    api_roles = {Role(id=41, name='name', colour=33, permissions=0x8, position=1)}
    guild_roles = {Role(id=41, name='name', colour=33, permissions=0x8, position=1)}

    assert get_roles_for_sync(guild_roles, api_roles) == (set(), set(), set())


def test_get_roles_for_sync_returns_roles_to_update_with_non_id_diff():
    api_roles = {Role(id=41, name='old name', colour=35, permissions=0x8, position=1)}
    guild_roles = {Role(id=41, name='new name', colour=33, permissions=0x8, position=2)}

    assert get_roles_for_sync(guild_roles, api_roles) == (
        set(),
        guild_roles,
        set(),
    )


def test_get_roles_only_returns_roles_that_require_update():
    api_roles = {
        Role(id=41, name='old name', colour=33, permissions=0x8, position=1),
        Role(id=53, name='other role', colour=55, permissions=0, position=3)
    }
    guild_roles = {
        Role(id=41, name='new name', colour=35, permissions=0x8, position=2),
        Role(id=53, name='other role', colour=55, permissions=0, position=3)
    }

    assert get_roles_for_sync(guild_roles, api_roles) == (
        set(),
        {Role(id=41, name='new name', colour=35, permissions=0x8, position=2)},
        set(),
    )


def test_get_roles_returns_new_roles_in_first_tuple_element():
    api_roles = {
        Role(id=41, name='name', colour=35, permissions=0x8, position=1),
    }
    guild_roles = {
        Role(id=41, name='name', colour=35, permissions=0x8, position=1),
        Role(id=53, name='other role', colour=55, permissions=0, position=2)
    }

    assert get_roles_for_sync(guild_roles, api_roles) == (
        {Role(id=53, name='other role', colour=55, permissions=0, position=2)},
        set(),
        set(),
    )


def test_get_roles_returns_roles_to_update_and_new_roles():
    api_roles = {
        Role(id=41, name='old name', colour=35, permissions=0x8, position=1),
    }
    guild_roles = {
        Role(id=41, name='new name', colour=40, permissions=0x16, position=2),
        Role(id=53, name='other role', colour=55, permissions=0, position=3)
    }

    assert get_roles_for_sync(guild_roles, api_roles) == (
        {Role(id=53, name='other role', colour=55, permissions=0, position=3)},
        {Role(id=41, name='new name', colour=40, permissions=0x16, position=2)},
        set(),
    )


def test_get_roles_returns_roles_to_delete():
    api_roles = {
        Role(id=41, name='name', colour=35, permissions=0x8, position=1),
        Role(id=61, name='to delete', colour=99, permissions=0x9, position=2),
    }
    guild_roles = {
        Role(id=41, name='name', colour=35, permissions=0x8, position=1),
    }

    assert get_roles_for_sync(guild_roles, api_roles) == (
        set(),
        set(),
        {Role(id=61, name='to delete', colour=99, permissions=0x9, position=2)},
    )


def test_get_roles_returns_roles_to_delete_update_and_new_roles():
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

    assert get_roles_for_sync(guild_roles, api_roles) == (
        {Role(id=81, name='to create', colour=99, permissions=0x9, position=4)},
        {Role(id=71, name='updated', colour=101, permissions=0x5, position=3)},
        {Role(id=61, name='to delete', colour=99, permissions=0x9, position=2)},
    )
