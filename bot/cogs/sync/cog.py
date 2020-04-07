import logging
from typing import Any, Dict

from discord import Member, Role, User
from discord.ext import commands
from discord.ext.commands import Cog, Context

from bot import constants
from bot.api import ResponseCodeError
from bot.bot import Bot
from bot.cogs.sync import syncers

log = logging.getLogger(__name__)


class Sync(Cog):
    """Captures relevant events and sends them to the site."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.role_syncer = syncers.RoleSyncer(self.bot)
        self.user_syncer = syncers.UserSyncer(self.bot)

        self.bot.loop.create_task(self.sync_guild())

    async def sync_guild(self) -> None:
        """Syncs the roles/users of the guild with the database."""
        await self.bot.wait_until_guild_available()

        guild = self.bot.get_guild(constants.Guild.id)
        if guild is None:
            return

        for syncer in (self.role_syncer, self.user_syncer):
            await syncer.sync(guild)

    async def patch_user(self, user_id: int, updated_information: Dict[str, Any]) -> None:
        """Send a PATCH request to partially update a user in the database."""
        try:
            await self.bot.api_client.patch(f"bot/users/{user_id}", json=updated_information)
        except ResponseCodeError as e:
            if e.response.status != 404:
                raise
            log.warning("Unable to update user, got 404. Assuming race condition from join event.")

    @Cog.listener()
    async def on_guild_role_create(self, role: Role) -> None:
        """Adds newly create role to the database table over the API."""
        await self.bot.api_client.post(
            'bot/roles',
            json={
                'colour': role.colour.value,
                'id': role.id,
                'name': role.name,
                'permissions': role.permissions.value,
                'position': role.position,
            }
        )

    @Cog.listener()
    async def on_guild_role_delete(self, role: Role) -> None:
        """Deletes role from the database when it's deleted from the guild."""
        await self.bot.api_client.delete(f'bot/roles/{role.id}')

    @Cog.listener()
    async def on_guild_role_update(self, before: Role, after: Role) -> None:
        """Syncs role with the database if any of the stored attributes were updated."""
        was_updated = (
            before.name != after.name or before.colour != after.colour or before.permissions != after.permissions or (
                before.position != after.position
            )
        )

        if was_updated:
            await self.bot.api_client.put(
                f'bot/roles/{after.id}',
                json={
                    'colour': after.colour.value,
                    'id': after.id,
                    'name': after.name,
                    'permissions': after.permissions.value,
                    'position': after.position,
                }
            )

    @Cog.listener()
    async def on_member_join(self, member: Member) -> None:
        """
        Adds a new user or updates existing user to the database when a member joins the guild.

        If the joining member is a user that is already known to the database (i.e., a user that
        previously left), it will update the user's information. If the user is not yet known by
        the database, the user is added.
        """
        packed = {
            'avatar_hash': member.avatar,
            'discriminator': int(member.discriminator),
            'id': member.id,
            'in_guild': True,
            'name': member.name,
            'roles': sorted(role.id for role in member.roles)
        }

        got_error = False

        try:
            # First try an update of the user to set the `in_guild` field and other
            # fields that may have changed since the last time we've seen them.
            await self.bot.api_client.put(f'bot/users/{member.id}', json=packed)

        except ResponseCodeError as e:
            # If we didn't get 404, something else broke - propagate it up.
            if e.response.status != 404:
                raise

            got_error = True  # yikes

        if got_error:
            # If we got `404`, the user is new. Create them.
            await self.bot.api_client.post('bot/users', json=packed)

    @Cog.listener()
    async def on_member_remove(self, member: Member) -> None:
        """Set the in_guild field to False when a member leaves the guild."""
        await self.patch_user(member.id, updated_information={"in_guild": False})

    @Cog.listener()
    async def on_member_update(self, before: Member, after: Member) -> None:
        """Update the roles of the member in the database if a change is detected."""
        if before.roles != after.roles:
            updated_information = {"roles": sorted(role.id for role in after.roles)}
            await self.patch_user(after.id, updated_information=updated_information)

    @Cog.listener()
    async def on_user_update(self, before: User, after: User) -> None:
        """Update the user information in the database if a relevant change is detected."""
        attrs = ("name", "discriminator", "avatar")
        if any(getattr(before, attr) != getattr(after, attr) for attr in attrs):
            updated_information = {
                "name": after.name,
                "discriminator": int(after.discriminator),
                "avatar_hash": after.avatar,
            }
            await self.patch_user(after.id, updated_information=updated_information)

    @commands.group(name='sync')
    @commands.has_permissions(administrator=True)
    async def sync_group(self, ctx: Context) -> None:
        """Run synchronizations between the bot and site manually."""

    @sync_group.command(name='roles')
    @commands.has_permissions(administrator=True)
    async def sync_roles_command(self, ctx: Context) -> None:
        """Manually synchronise the guild's roles with the roles on the site."""
        await self.role_syncer.sync(ctx.guild, ctx)

    @sync_group.command(name='users')
    @commands.has_permissions(administrator=True)
    async def sync_users_command(self, ctx: Context) -> None:
        """Manually synchronise the guild's users with the users on the site."""
        await self.user_syncer.sync(ctx.guild, ctx)
