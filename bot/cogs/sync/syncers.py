import abc
import logging
import typing as t
from collections import namedtuple

from discord import Guild, HTTPException, Message
from discord.ext.commands import Context

from bot import constants
from bot.bot import Bot

log = logging.getLogger(__name__)

# These objects are declared as namedtuples because tuples are hashable,
# something that we make use of when diffing site roles against guild roles.
Role = namedtuple('Role', ('id', 'name', 'colour', 'permissions', 'position'))
User = namedtuple('User', ('id', 'name', 'discriminator', 'avatar_hash', 'roles', 'in_guild'))

_T = t.TypeVar("_T")


class Diff(t.NamedTuple, t.Generic[_T]):
    """The differences between the Discord cache and the contents of the database."""

    created: t.Set[_T] = {}
    updated: t.Set[_T] = {}
    deleted: t.Set[_T] = {}


class Syncer(abc.ABC, t.Generic[_T]):
    """Base class for synchronising the database with objects in the Discord cache."""

    CONFIRM_TIMEOUT = 60 * 5  # 5 minutes
    MAX_DIFF = 10

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """The name of the syncer; used in output messages and logging."""
        raise NotImplementedError

    async def _confirm(self, message: t.Optional[Message] = None) -> bool:
        """
        Send a prompt to confirm or abort a sync using reactions and return True if confirmed.

        If a message is given, it is edited to display the prompt and reactions. Otherwise, a new
        message is sent to the dev-core channel and mentions the core developers role.
        """
        allowed_emoji = (constants.Emojis.check_mark, constants.Emojis.cross_mark)
        msg_content = (
            f'Possible cache issue while syncing {self.name}s. '
            f'Found no {self.name}s or more than {self.MAX_DIFF} {self.name}s were changed. '
            f'React to confirm or abort the sync.'
        )

        # Send to core developers if it's an automatic sync.
        if not message:
            channel = self.bot.get_channel(constants.Channels.devcore)

            if not channel:
                try:
                    channel = self.bot.fetch_channel(constants.Channels.devcore)
                except HTTPException:
                    log.exception(
                        f"Failed to fetch channel for sending sync confirmation prompt; "
                        f"aborting {self.name} sync."
                    )
                    return False

            message = await channel.send(f"<@&{constants.Roles.core_developer}> {msg_content}")
        else:
            message = await message.edit(content=f"{message.author.mention} {msg_content}")

        # Add the initial reactions.
        for emoji in allowed_emoji:
            await message.add_reaction(emoji)

        def check(_reaction, user):  # noqa: TYP
            # Skip author check for auto syncs
            return (
                _reaction.message.id == message.id
                and True if message.author.bot else user == message.author
                and str(_reaction.emoji) in allowed_emoji
            )

        reaction = None
        try:
            reaction, _ = await self.bot.wait_for(
                'reaction_add',
                check=check,
                timeout=self.CONFIRM_TIMEOUT
            )
        except TimeoutError:
            # reaction will remain none thus sync will be aborted in the finally block below.
            pass
        finally:
            if str(reaction) == constants.Emojis.check_mark:
                await message.edit(content=f':ok_hand: {self.name} sync will proceed.')
                return True
            else:
                log.warning(f"{self.name} syncer aborted!")
                await message.edit(content=f':x: {self.name} sync aborted!')
                return False

    @abc.abstractmethod
    async def _get_diff(self, guild: Guild) -> Diff[_T]:
        """Return the difference between the cache of `guild` and the database."""
        raise NotImplementedError

    @abc.abstractmethod
    async def _sync(self, diff: Diff[_T]) -> None:
        """Perform the API calls for synchronisation."""
        raise NotImplementedError

    async def sync(self, guild: Guild, ctx: t.Optional[Context] = None) -> None:
        """
        Synchronise the database with the cache of `guild`.

        If the differences between the cache and the database are greater than `MAX_DIFF`, then
        a confirmation prompt will be sent to the dev-core channel. The confirmation can be
        optionally redirect to `ctx` instead.
        """
        log.info(f"Starting {self.name} syncer.")
        if ctx:
            message = await ctx.send(f"📊 Synchronising {self.name}s.")

        diff = await self._get_diff(guild)
        total = sum(map(len, diff))

        if total > self.MAX_DIFF and not await self._confirm(ctx):
            return  # Sync aborted.

        await self._sync(diff)

        results = ", ".join(f"{name} `{len(total)}`" for name, total in diff._asdict().items())
        log.info(f"{self.name} syncer finished: {results}.")
        if ctx:
            await message.edit(
                content=f":ok_hand: Synchronisation of {self.name}s complete: {results}"
            )


class RoleSyncer(Syncer[Role]):
    """Synchronise the database with roles in the cache."""

    name = "role"

    async def _get_diff(self, guild: Guild) -> Diff[Role]:
        """Return the difference of roles between the cache of `guild` and the database."""
        roles = await self.bot.api_client.get('bot/roles')

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

    async def _sync(self, diff: Diff[Role]) -> None:
        """Synchronise the database with the role cache of `guild`."""
        for role in diff.created:
            await self.bot.api_client.post('bot/roles', json={**role._asdict()})

        for role in diff.updated:
            await self.bot.api_client.put(f'bot/roles/{role.id}', json={**role._asdict()})

        for role in diff.deleted:
            await self.bot.api_client.delete(f'bot/roles/{role.id}')


class UserSyncer(Syncer[User]):
    """Synchronise the database with users in the cache."""

    name = "user"

    async def _get_diff(self, guild: Guild) -> Diff[User]:
        """Return the difference of users between the cache of `guild` and the database."""
        users = await self.bot.api_client.get('bot/users')

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

    async def _sync(self, diff: Diff[User]) -> None:
        """Synchronise the database with the user cache of `guild`."""
        for user in diff.created:
            await self.bot.api_client.post('bot/users', json={**user._asdict()})

        for user in diff.updated:
            await self.bot.api_client.put(f'bot/users/{user.id}', json={**user._asdict()})
