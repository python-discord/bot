import logging
from typing import Callable, Coroutine

import discord

import bot
from bot import constants
from bot.exts.help_channels import _caches, _channel
from bot.utils.scheduling import Scheduler

log = logging.getLogger(__name__)
CoroutineFunc = Callable[..., Coroutine]


async def add_cooldown_role(member: discord.Member) -> None:
    """Add the help cooldown role to `member`."""
    log.trace(f"Adding cooldown role for {member} ({member.id}).")
    await _change_cooldown_role(member, member.add_roles)


async def check_cooldowns(scheduler: Scheduler) -> None:
    """Remove expired cooldowns and re-schedule active ones."""
    log.trace("Checking all cooldowns to remove or re-schedule them.")
    guild = bot.instance.get_guild(constants.Guild.id)
    cooldown = constants.HelpChannels.claim_minutes * 60

    for channel_id, member_id in await _caches.claimants.items():
        member = guild.get_member(member_id)
        if not member:
            continue  # Member probably left the guild.

        in_use_time = await _channel.get_in_use_time(channel_id)

        if not in_use_time or in_use_time.seconds > cooldown:
            # Remove the role if no claim time could be retrieved or if the cooldown expired.
            # Since the channel is in the claimants cache, it is definitely strange for a time
            # to not exist. However, it isn't a reason to keep the user stuck with a cooldown.
            await remove_cooldown_role(member)
        else:
            # The member is still on a cooldown; re-schedule it for the remaining time.
            delay = cooldown - in_use_time.seconds
            scheduler.schedule_later(delay, member.id, remove_cooldown_role(member))


async def remove_cooldown_role(member: discord.Member) -> None:
    """Remove the help cooldown role from `member`."""
    log.trace(f"Removing cooldown role for {member} ({member.id}).")
    await _change_cooldown_role(member, member.remove_roles)


async def revoke_send_permissions(member: discord.Member, scheduler: Scheduler) -> None:
    """
    Disallow `member` to send messages in the Available category for a certain time.

    The time until permissions are reinstated can be configured with
    `HelpChannels.claim_minutes`.
    """
    log.trace(
        f"Revoking {member}'s ({member.id}) send message permissions in the Available category."
    )

    await add_cooldown_role(member)

    # Cancel the existing task, if any.
    # Would mean the user somehow bypassed the lack of permissions (e.g. user is guild owner).
    if member.id in scheduler:
        scheduler.cancel(member.id)

    delay = constants.HelpChannels.claim_minutes * 60
    scheduler.schedule_later(delay, member.id, remove_cooldown_role(member))


async def _change_cooldown_role(member: discord.Member, coro_func: CoroutineFunc) -> None:
    """
    Change `member`'s cooldown role via awaiting `coro_func` and handle errors.

    `coro_func` is intended to be `discord.Member.add_roles` or `discord.Member.remove_roles`.
    """
    guild = bot.instance.get_guild(constants.Guild.id)
    role = guild.get_role(constants.Roles.help_cooldown)
    if role is None:
        log.warning(f"Help cooldown role ({constants.Roles.help_cooldown}) could not be found!")
        return

    try:
        await coro_func(role)
    except discord.NotFound:
        log.debug(f"Failed to change role for {member} ({member.id}): member not found")
    except discord.Forbidden:
        log.debug(
            f"Forbidden to change role for {member} ({member.id}); "
            f"possibly due to role hierarchy"
        )
    except discord.HTTPException as e:
        log.error(f"Failed to change role for {member} ({member.id}): {e.status} {e.code}")
