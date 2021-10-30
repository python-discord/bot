import typing as t

import discord
from discord.ext.commands import Bot

from bot.log import get_logger

log = get_logger(__name__)


async def get_or_fetch_member(guild: discord.Guild, member_id: int) -> t.Optional[discord.Member]:
    """
    Attempt to get a member from cache; on failure fetch from the API.

    Return `None` to indicate the member could not be found.
    """
    if member := guild.get_member(member_id):
        log.trace("%s retrieved from cache.", member)
    else:
        try:
            member = await guild.fetch_member(member_id)
        except discord.errors.NotFound:
            log.trace("Failed to fetch %d from API.", member_id)
            return None
        log.trace("%s fetched from API.", member)
    return member


async def get_or_fetch_user(bot: Bot, user_id: int) -> t.Optional[discord.User]:
    """
    Attempt to get a user from cache; on failure fetch from the API.

    Return `None` to indicate the member could not be found.
    """
    if user := bot.get_user(user_id):
        log.trace("%s retrieved from cache.", user)
    else:
        try:
            user = await bot.fetch_user(user_id)
        except discord.errors.NotFound:
            log.trace("Failed to fetch %d from API.", user_id)
            return None
        log.trace("%s fetched from API.", user)
    return user
