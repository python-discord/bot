import typing as t

import discord

from bot.log import get_logger

log = get_logger(__name__)


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
