import abc
import typing as t
from collections import namedtuple

from discord import Guild

from bot.api import APIClient

_T = t.TypeVar("_T")

# These objects are declared as namedtuples because tuples are hashable,
# something that we make use of when diffing site roles against guild roles.
Role = namedtuple('Role', ('id', 'name', 'colour', 'permissions', 'position'))
User = namedtuple('User', ('id', 'name', 'discriminator', 'avatar_hash', 'roles', 'in_guild'))


class Diff(t.NamedTuple, t.Generic[_T]):
    """The differences between the Discord cache and the contents of the database."""

    created: t.Optional[t.Set[_T]] = None
    updated: t.Optional[t.Set[_T]] = None
    deleted: t.Optional[t.Set[_T]] = None


class Syncer(abc.ABC, t.Generic[_T]):
    """Base class for synchronising the database with objects in the Discord cache."""

    def __init__(self, api_client: APIClient) -> None:
        self.api_client = api_client

    @abc.abstractmethod
    async def get_diff(self, guild: Guild) -> Diff[_T]:
        """Return objects of `guild` with which to synchronise the database."""
        raise NotImplementedError

    @abc.abstractmethod
    async def sync(self, diff: Diff[_T]) -> None:
        """Synchronise the database with the given `diff`."""
        raise NotImplementedError


class RoleSyncer(Syncer[Role]):
    """Synchronise the database with roles in the cache."""

    async def get_diff(self, guild: Guild) -> Diff[Role]:
        """Return the roles of `guild` with which to synchronise the database."""
        roles = await self.api_client.get('bot/roles')

        # Pack DB roles and guild roles into one common, hashable format.
        # They're hashable so that they're easily comparable with sets later.
        db_roles = {Role(**role_dict) for role_dict in roles}
        guild_roles = {
            Role(
                id=role.id,
                name=role.name,
                colour=role.colour.value,
                permissions=role.permissions.value,
                position=role.position,
            )
            for role in guild.roles
        }

        guild_role_ids = {role.id for role in guild_roles}
        api_role_ids = {role.id for role in db_roles}
        new_role_ids = guild_role_ids - api_role_ids
        deleted_role_ids = api_role_ids - guild_role_ids

        # New roles are those which are on the cached guild but not on the
        # DB guild, going by the role ID. We need to send them in for creation.
        roles_to_create = {role for role in guild_roles if role.id in new_role_ids}
        roles_to_update = guild_roles - db_roles - roles_to_create
        roles_to_delete = {role for role in db_roles if role.id in deleted_role_ids}

        return Diff(roles_to_create, roles_to_update, roles_to_delete)

    async def sync(self, diff: Diff[Role]) -> None:
        """Synchronise roles in the database with the given `diff`."""
        for role in diff.created:
            await self.api_client.post('bot/roles', json={**role._asdict()})

        for role in diff.updated:
            await self.api_client.put(f'bot/roles/{role.id}', json={**role._asdict()})

        for role in diff.deleted:
            await self.api_client.delete(f'bot/roles/{role.id}')


class UserSyncer(Syncer[User]):
    """Synchronise the database with users in the cache."""

    async def get_diff(self, guild: Guild) -> Diff[User]:
        """Return the users of `guild` with which to synchronise the database."""
        users = await self.api_client.get('bot/users')

        # Pack DB roles and guild roles into one common, hashable format.
        # They're hashable so that they're easily comparable with sets later.
        db_users = {
            user_dict['id']: User(
                roles=tuple(sorted(user_dict.pop('roles'))),
                **user_dict
            )
            for user_dict in users
        }
        guild_users = {
            member.id: User(
                id=member.id,
                name=member.name,
                discriminator=int(member.discriminator),
                avatar_hash=member.avatar,
                roles=tuple(sorted(role.id for role in member.roles)),
                in_guild=True
            )
            for member in guild.members
        }

        users_to_create = set()
        users_to_update = set()

        for db_user in db_users.values():
            guild_user = guild_users.get(db_user.id)
            if guild_user is not None:
                if db_user != guild_user:
                    users_to_update.add(guild_user)

            elif db_user.in_guild:
                # The user is known in the DB but not the guild, and the
                # DB currently specifies that the user is a member of the guild.
                # This means that the user has left since the last sync.
                # Update the `in_guild` attribute of the user on the site
                # to signify that the user left.
                new_api_user = db_user._replace(in_guild=False)
                users_to_update.add(new_api_user)

        new_user_ids = set(guild_users.keys()) - set(db_users.keys())
        for user_id in new_user_ids:
            # The user is known on the guild but not on the API. This means
            # that the user has joined since the last sync. Create it.
            new_user = guild_users[user_id]
            users_to_create.add(new_user)

        return Diff(users_to_create, users_to_update)

    async def sync(self, diff: Diff[User]) -> None:
        """Synchronise users in the database with the given `diff`."""
        for user in diff.created:
            await self.api_client.post('bot/users', json={**user._asdict()})

        for user in diff.updated:
            await self.api_client.put(f'bot/users/{user.id}', json={**user._asdict()})
