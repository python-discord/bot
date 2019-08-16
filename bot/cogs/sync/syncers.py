from collections import namedtuple
from typing import Dict, Set, Tuple

from discord import Guild
from discord.ext.commands import Bot

# These objects are declared as namedtuples because tuples are hashable,
# something that we make use of when diffing site roles against guild roles.
Role = namedtuple('Role', ('id', 'name', 'colour', 'permissions', 'position'))
User = namedtuple('User', ('id', 'name', 'discriminator', 'avatar_hash', 'roles', 'in_guild'))


def get_roles_for_sync(
        guild_roles: Set[Role], api_roles: Set[Role]
) -> Tuple[Set[Role], Set[Role], Set[Role]]:
    """
    Determine which roles should be created or updated on the site.

    Arguments:
        guild_roles (Set[Role]):
            Roles that were found on the guild at startup.

        api_roles (Set[Role]):
            Roles that were retrieved from the API at startup.

    Returns:
        Tuple[Set[Role], Set[Role]]:
            A tuple with two elements. The first element represents
            roles to be created on the site, meaning that they were
            present on the cached guild but not on the API. The second
            element represents roles to be updated, meaning they were
            present on both the cached guild and the API but non-ID
            fields have changed inbetween.
    """

    guild_role_ids = {role.id for role in guild_roles}
    api_role_ids = {role.id for role in api_roles}
    new_role_ids = guild_role_ids - api_role_ids
    deleted_role_ids = api_role_ids - guild_role_ids

    # New roles are those which are on the cached guild but not on the
    # API guild, going by the role ID. We need to send them in for creation.
    roles_to_create = {role for role in guild_roles if role.id in new_role_ids}
    roles_to_update = guild_roles - api_roles - roles_to_create
    roles_to_delete = {role for role in api_roles if role.id in deleted_role_ids}
    return roles_to_create, roles_to_update, roles_to_delete


async def sync_roles(bot: Bot, guild: Guild) -> Tuple[Set[Role], Set[Role], Set[Role]]:
    """
    Synchronize roles found on the given `guild` with the ones on the API.

    Arguments:
        bot (discord.ext.commands.Bot):
            The bot instance that we're running with.

        guild (discord.Guild):
            The guild instance from the bot's cache
            to synchronize roles with.

    Returns:
        Tuple[int, int]:
            A tuple with two integers representing how many roles were created
            (element `0`) and how many roles were updated (element `1`).
    """

    roles = await bot.api_client.get('bot/roles')

    # Pack API roles and guild roles into one common format,
    # which is also hashable. We need hashability to be able
    # to compare these easily later using sets.
    api_roles = {Role(**role_dict) for role_dict in roles}
    guild_roles = {
        Role(
            id=role.id, name=role.name,
            colour=role.colour.value, permissions=role.permissions.value,
            position=role.position,
        )
        for role in guild.roles
    }
    roles_to_create, roles_to_update, roles_to_delete = get_roles_for_sync(guild_roles, api_roles)

    for role in roles_to_create:
        await bot.api_client.post(
            'bot/roles',
            json={
                'id': role.id,
                'name': role.name,
                'colour': role.colour,
                'permissions': role.permissions,
                'position': role.position,
            }
        )

    for role in roles_to_update:
        await bot.api_client.put(
            f'bot/roles/{role.id}',
            json={
                'id': role.id,
                'name': role.name,
                'colour': role.colour,
                'permissions': role.permissions,
                'position': role.position,
            }
        )

    for role in roles_to_delete:
        await bot.api_client.delete(f'bot/roles/{role.id}')

    return len(roles_to_create), len(roles_to_update), len(roles_to_delete)


def get_users_for_sync(
        guild_users: Dict[int, User], api_users: Dict[int, User]
) -> Tuple[Set[User], Set[User]]:
    """
    Determine which users should be created or updated on the website.

    Arguments:
        guild_users (Dict[int, User]):
            A mapping of user IDs to user data, populated from the
            guild cached on the running bot instance.

        api_users (Dict[int, User]):
            A mapping of user IDs to user data, populated from the API's
            current inventory of all users.

    Returns:
        Tuple[Set[User], Set[User]]:
            Two user sets as a tuple. The first element represents users
            to be created on the website, these are users that are present
            in the cached guild data but not in the API at all, going by
            their ID. The second element represents users to update. It is
            populated by users which are present on both the API and the
            guild, but where the attribute of a user on the API is not
            equal to the attribute of the user on the guild.
    """

    users_to_create = set()
    users_to_update = set()

    for api_user in api_users.values():
        guild_user = guild_users.get(api_user.id)
        if guild_user is not None:
            if api_user != guild_user:
                users_to_update.add(guild_user)

        elif api_user.in_guild:
            # The user is known on the API but not the guild, and the
            # API currently specifies that the user is a member of the guild.
            # This means that the user has left since the last sync.
            # Update the `in_guild` attribute of the user on the site
            # to signify that the user left.
            new_api_user = api_user._replace(in_guild=False)
            users_to_update.add(new_api_user)

    new_user_ids = set(guild_users.keys()) - set(api_users.keys())
    for user_id in new_user_ids:
        # The user is known on the guild but not on the API. This means
        # that the user has joined since the last sync. Create it.
        new_user = guild_users[user_id]
        users_to_create.add(new_user)

    return users_to_create, users_to_update


async def sync_users(bot: Bot, guild: Guild) -> Tuple[Set[Role], Set[Role], None]:
    """
    Synchronize users found on the given
    `guild` with the ones on the API.

    Arguments:
        bot (discord.ext.commands.Bot):
            The bot instance that we're running with.

        guild (discord.Guild):
            The guild instance from the bot's cache
            to synchronize roles with.

    Returns:
        Tuple[int, int]:
            A tuple with two integers representing how many users were created
            (element `0`) and how many users were updated (element `1`).
    """

    current_users = await bot.api_client.get('bot/users')

    # Pack API users and guild users into one common format,
    # which is also hashable. We need hashability to be able
    # to compare these easily later using sets.
    api_users = {
        user_dict['id']: User(
            roles=tuple(sorted(user_dict.pop('roles'))),
            **user_dict
        )
        for user_dict in current_users
    }
    guild_users = {
        member.id: User(
            id=member.id, name=member.name,
            discriminator=int(member.discriminator), avatar_hash=member.avatar,
            roles=tuple(sorted(role.id for role in member.roles)), in_guild=True
        )
        for member in guild.members
    }

    users_to_create, users_to_update = get_users_for_sync(guild_users, api_users)

    for user in users_to_create:
        await bot.api_client.post(
            'bot/users',
            json={
                'avatar_hash': user.avatar_hash,
                'discriminator': user.discriminator,
                'id': user.id,
                'in_guild': user.in_guild,
                'name': user.name,
                'roles': list(user.roles)
            }
        )

    for user in users_to_update:
        await bot.api_client.put(
            f'bot/users/{user.id}',
            json={
                'avatar_hash': user.avatar_hash,
                'discriminator': user.discriminator,
                'id': user.id,
                'in_guild': user.in_guild,
                'name': user.name,
                'roles': list(user.roles)
            }
        )

    return len(users_to_create), len(users_to_update), None
