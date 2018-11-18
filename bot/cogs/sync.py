import logging
from collections import namedtuple
from typing import Callable, Iterable

from discord import Guild, Role
from discord.ext.commands import Bot


log = logging.getLogger(__name__)
Role = namedtuple('Role', ('id', 'name', 'colour', 'permissions'))


async def sync_roles(bot: Bot, guild: Guild):
    """
    Synchronize roles found on the given `guild` with the ones on the API.
    """

    def convert_role(role: Role):
        return {
            'id': role.id,
            'name': role.name,
            'colour': role.colour,
            'permissions': role.permissions
        }

    roles = await bot.api_client.get('bot/roles')
    site_roles = {
        Role(**role_dict)
        for role_dict in roles
    }
    server_roles = {
        Role(
            id=role.id, name=role.name,
            colour=role.colour.value, permissions=role.permissions.value
        )
        for role in guild.roles
    }
    roles_to_update = server_roles - site_roles

    for role in roles_to_update:
        log.info(f"Updating role `{role.name}` on the site.")
        await bot.api_client.post(
            'bot/roles',
            json={
                'id': role.id,
                'name': role.name,
                'colour': role.colour,
                'permissions': role.permissions
            }
        )


async def sync_members(bot: Bot, guild: Guild):
    """
    Synchronize members found on the given `guild` with the ones on the API.
    """

    current_members = await bot.api_client.get('bot/members')


class Sync:
    """Captures relevant events and sends them to the site."""

    # The server to synchronize events on.
    # Note that setting this wrongly will result in things getting deleted
    # that possibly shouldn't be.
    SYNC_SERVER_ID = 267624335836053506

    # An iterable of callables that are called when the bot is ready.
    ON_READY_SYNCERS: Iterable[Callable[[Bot, Guild], None]] = (
        sync_roles,
    )

    def __init__(self, bot):
        self.bot = bot

    async def on_ready(self):
        guild = self.bot.get_guild(self.SYNC_SERVER_ID)
        if guild is not None:
            for syncer in self.ON_READY_SYNCERS:
                await syncer(self.bot, guild)


def setup(bot):
    bot.add_cog(Sync(bot))
    log.info("Cog loaded: Sync")
