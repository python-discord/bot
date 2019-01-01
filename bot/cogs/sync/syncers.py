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


def get_roles_for_update(guild_roles: Set[Role], api_roles: Set[Role]) -> Set[Role]:
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

    return guild_roles - api_roles


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
    roles_to_update = get_roles_for_update(guild_roles, api_roles)

    for role in roles_to_update:
        log.info(f"Updating role `{role.name}` on the site.")
        await bot.api_client.put(
            'bot/roles',
            json={
                'id': role.id,
                'name': role.name,
                'colour': role.colour,
                'permissions': role.permissions
            }
        )


def get_users_for_update(
        guild_users: Dict[int, User], api_users: Dict[int, User]
) -> ValuesView[User]:
    """
    Obtain a set of users to update on the website.
    """

    api_user_ids = set(api_users.keys())
    guild_user_ids = set(guild_users.keys())
    left_user_ids = api_user_ids - guild_user_ids

    api_users.update(guild_users)
    for left_id in left_user_ids:
        if left_id in api_users:
            user = api_users[left_id]
            log.debug(
                "User `%s#%s` (`%d`) left since the last sync, updating `in_guild` field.",
                user.name, user.discriminator, user.discriminator
            )
            api_users[left_id]._replace(in_guild=False)

    return api_users.values()


# Taken from `https://docs.python.org/3.7/library/itertools.html#itertools-recipes`.
def chunk_by(iterable, n, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    args = [iter(iterable)] * n
    return itertools.zip_longest(*args, fillvalue=fillvalue)


async def sync_users(bot: Bot, guild: Guild):
    """
    Synchronize users found on the given
    `guild` with the ones on the API.
    """

    current_users = await bot.api_client.get('bot/users')
    api_users = {
        user_dict['id']: User(
            roles=set(user_dict.pop('roles')),
            **user_dict
        )
        for user_dict in current_users
    }
    guild_users = {
        member.id: User(
            id=member.id, name=member.name,
            discriminator=member.discriminator, avatar_hash=member.avatar,
            roles={role.id for role in member.roles}, in_guild=True
        )
        for member in guild.members
    }
    users_to_update = get_users_for_update(guild_users, api_users)
    log.info("Updating a total of `%d` users on the site.", len(users_to_update))
    for user in users_to_update:
        await bot.api_client.put(
            'bot/users/' + str(user.id),
            json={
                'avatar': user.avatar_hash,
                'discriminator': user.discriminator,
                'id': user.id,
                'in_guild': user.in_guild,
                'name': user.name,
                'roles': list(user.roles)
            }
        )
    log.info("User update complete.")
