import itertools
import logging
from collections import namedtuple
from typing import Dict, Set, ValuesView

from discord import Guild
from discord.ext.commands import Bot

log = logging.getLogger(__name__)

# These objects are declared as namedtuples because tuples are hashable,
# something that we make use of when diffing site roles against guild roles.
Role = namedtuple('Role', ('id', 'name', 'colour', 'permissions'))
User = namedtuple('User', ('id', 'name', 'discriminator', 'avatar_hash', 'roles', 'in_guild'))


def get_roles_for_sync(guild_roles: Set[Role], api_roles: Set[Role]) -> Set[Role]:
    """
    Determine which roles should be updated on the site.

    Arguments:
        guild_roles (Set[Role]):
            Roles that were found on the guild at startup.

        api_roles (Set[Role]):
            Roles that were retrieved from the API at startup.

    Returns:
        Set[Role]:
            Roles to be sent to the site for an update or insert.
    """

    guild_role_ids = {role.id for role in guild_roles}
    api_role_ids = {role.id for role in api_roles}
    new_role_ids = guild_role_ids - api_role_ids

    roles_to_create = {role for role in guild_roles if role.id in new_role_ids}
    roles_to_update = guild_roles - api_roles - roles_to_create
    return roles_to_create, roles_to_update


async def sync_roles(bot: Bot, guild: Guild):
    """
    Synchronize roles found on the given `guild` with the ones on the API.
    """

    roles = await bot.api_client.get('bot/roles')
    api_roles = {Role(**role_dict) for role_dict in roles}
    guild_roles = {
        Role(
            id=role.id, name=role.name,
            colour=role.colour.value, permissions=role.permissions.value
        )
        for role in guild.roles
    }
    roles_to_create, roles_to_update = get_roles_for_sync(guild_roles, api_roles)
    for role in roles_to_create:
        log.info(f"Creating role `{role.name}` on the site.")
        await bot.api_client.post(
            'bot/roles',
            json={
                'id': role.id,
                'name': role.name,
                'colour': role.colour,
                'permissions': role.permissions
            }
        )

    for role in roles_to_update:
        log.info(f"Updating role `{role.name}` on the site.")
        await bot.api_client.put(
            'bot/roles/' + str(role.id),
            json={
                'id': role.id,
                'name': role.name,
                'colour': role.colour,
                'permissions': role.permissions
            }
        )


def get_users_for_sync(
        guild_users: Dict[int, User], api_users: Dict[int, User]
) -> ValuesView[User]:
    """
    Obtain a set of users to update on the website.
    """

    users_to_create = set()
    users_to_update = set()

    for api_user in api_users.values():
        guild_user = guild_users.get(api_user.id)
        if guild_user is not None:
            if api_user != guild_user:
                users_to_update.add(guild_user)
        else:
            # User left
            api_user._replace(in_guild=False)
            users_to_update.add(guild_user)

    new_user_ids = set(guild_users.keys()) - set(api_users.keys())
    for user_id in new_user_ids:
        # User joined
        new_user = guild_users[user_id]
        users_to_create.add(new_user)

    return users_to_create, users_to_update


async def sync_users(bot: Bot, guild: Guild):
    """
    Synchronize users found on the given
    `guild` with the ones on the API.
    """

    current_users = await bot.api_client.get('bot/users')
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
    log.info("Creating a total of `%d` users on the site.", len(users_to_create))
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
    log.info("User creation complete.")

    log.info("Updating a total of `%d` users on the site.", len(users_to_update))
    for user in users_to_update:
        if user is None:  # ??
            continue

        await bot.api_client.put(
            'bot/users/' + str(user.id),
            json={
                'avatar_hash': user.avatar_hash,
                'discriminator': user.discriminator,
                'id': user.id,
                'in_guild': user.in_guild,
                'name': user.name,
                'roles': list(user.roles)
            }
        )
    log.info("User update complete.")
