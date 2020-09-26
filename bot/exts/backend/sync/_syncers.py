import abc
import logging
import typing as t
from collections import namedtuple

from discord import Guild
from discord.ext.commands import Context

from bot.api import ResponseCodeError
from bot.bot import Bot

log = logging.getLogger(__name__)

# These objects are declared as namedtuples because tuples are hashable,
# something that we make use of when diffing site roles against guild roles.
_Role = namedtuple('Role', ('id', 'name', 'colour', 'permissions', 'position'))
_User = namedtuple('User', ('id', 'name', 'discriminator', 'roles', 'in_guild'))
_Diff = namedtuple('Diff', ('created', 'updated', 'deleted'))


class Syncer(abc.ABC):
    """Base class for synchronising the database with objects in the Discord cache."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """The name of the syncer; used in output messages and logging."""
        raise NotImplementedError  # pragma: no cover

    @abc.abstractmethod
    async def _get_diff(self, guild: Guild) -> _Diff:
        """Return the difference between the cache of `guild` and the database."""
        raise NotImplementedError  # pragma: no cover

    @abc.abstractmethod
    async def _sync(self, diff: _Diff) -> None:
        """Perform the API calls for synchronisation."""
        raise NotImplementedError  # pragma: no cover

    async def sync(self, guild: Guild, ctx: t.Optional[Context] = None) -> None:
        """
        Synchronise the database with the cache of `guild`.

        If `ctx` is given, send a message with the results.
        """
        log.info(f"Starting {self.name} syncer.")

        if ctx:
            message = await ctx.send(f"📊 Synchronising {self.name}s.")
        else:
            message = None
        diff = await self._get_diff(guild)

        try:
            await self._sync(diff)
        except ResponseCodeError as e:
            log.exception(f"{self.name} syncer failed!")

            # Don't show response text because it's probably some really long HTML.
            results = f"status {e.status}\n```{e.response_json or 'See log output for details'}```"
            content = f":x: Synchronisation of {self.name}s failed: {results}"
        else:
            diff_dict = diff._asdict()
            results = (f"{name} `{len(val)}`" for name, val in diff_dict.items() if val is not None)
            results = ", ".join(results)

            log.info(f"{self.name} syncer finished: {results}.")
            content = f":ok_hand: Synchronisation of {self.name}s complete: {results}"

        if message:
            await message.edit(content=content)


class RoleSyncer(Syncer):
    """Synchronise the database with roles in the cache."""

    name = "role"

    async def _get_diff(self, guild: Guild) -> _Diff:
        """Return the difference of roles between the cache of `guild` and the database."""
        log.trace("Getting the diff for roles.")
        roles = await self.bot.api_client.get('bot/roles')

        # Pack DB roles and guild roles into one common, hashable format.
        # They're hashable so that they're easily comparable with sets later.
        db_roles = {_Role(**role_dict) for role_dict in roles}
        guild_roles = {
            _Role(
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

        return _Diff(roles_to_create, roles_to_update, roles_to_delete)

    async def _sync(self, diff: _Diff) -> None:
        """Synchronise the database with the role cache of `guild`."""
        log.trace("Syncing created roles...")
        for role in diff.created:
            await self.bot.api_client.post('bot/roles', json=role._asdict())

        log.trace("Syncing updated roles...")
        for role in diff.updated:
            await self.bot.api_client.put(f'bot/roles/{role.id}', json=role._asdict())

        log.trace("Syncing deleted roles...")
        for role in diff.deleted:
            await self.bot.api_client.delete(f'bot/roles/{role.id}')


class UserSyncer(Syncer):
    """Synchronise the database with users in the cache."""

    name = "user"

    async def _get_diff(self, guild: Guild) -> _Diff:
        """Return the difference of users between the cache of `guild` and the database."""
        log.trace("Getting the diff for users.")
        users = await self.bot.api_client.get('bot/users')

        # Pack DB roles and guild roles into one common, hashable format.
        # They're hashable so that they're easily comparable with sets later.
        db_users = {
            user_dict['id']: _User(
                roles=tuple(sorted(user_dict.pop('roles'))),
                **user_dict
            )
            for user_dict in users
        }
        guild_users = {
            member.id: _User(
                id=member.id,
                name=member.name,
                discriminator=int(member.discriminator),
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

        return _Diff(users_to_create, users_to_update, None)

    async def _sync(self, diff: _Diff) -> None:
        """Synchronise the database with the user cache of `guild`."""
        log.trace("Syncing created users...")
        for user in diff.created:
            await self.bot.api_client.post('bot/users', json=user._asdict())

        log.trace("Syncing updated users...")
        for user in diff.updated:
            await self.bot.api_client.put(f'bot/users/{user.id}', json=user._asdict())
