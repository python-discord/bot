import typing as t

import discord

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


async def handle_role_change(
    member: discord.Member,
    coro: t.Callable[..., t.Coroutine],
    role: discord.Role
) -> None:
    """
    Change `member`'s cooldown role via awaiting `coro` and handle errors.

    `coro` is intended to be `discord.Member.add_roles` or `discord.Member.remove_roles`.
    """
    try:
        await coro(role)
    except discord.NotFound:
        log.debug(f"Failed to change role for {member} ({member.id}): member not found")
    except discord.Forbidden:
        log.debug(
            f"Forbidden to change role for {member} ({member.id}); "
            f"possibly due to role hierarchy"
        )
    except discord.HTTPException as e:
        log.error(f"Failed to change role for {member} ({member.id}): {e.status} {e.code}")
