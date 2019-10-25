import datetime
import logging
from typing import Callable, Iterable

from discord.ext.commands import BucketType, Cog, Command, CommandOnCooldown, Context, Cooldown, CooldownMapping

log = logging.getLogger(__name__)


def with_role_check(ctx: Context, *role_ids: int) -> bool:
    """Returns True if the user has any one of the roles in role_ids."""
    if not ctx.guild:  # Return False in a DM
        log.trace(f"{ctx.author} tried to use the '{ctx.command.name}'command from a DM. "
                  "This command is restricted by the with_role decorator. Rejecting request.")
        return False

    for role in ctx.author.roles:
        if role.id in role_ids:
            log.trace(f"{ctx.author} has the '{role.name}' role, and passes the check.")
            return True

    log.trace(f"{ctx.author} does not have the required role to use "
              f"the '{ctx.command.name}' command, so the request is rejected.")
    return False


def without_role_check(ctx: Context, *role_ids: int) -> bool:
    """Returns True if the user does not have any of the roles in role_ids."""
    if not ctx.guild:  # Return False in a DM
        log.trace(f"{ctx.author} tried to use the '{ctx.command.name}' command from a DM. "
                  "This command is restricted by the without_role decorator. Rejecting request.")
        return False

    author_roles = [role.id for role in ctx.author.roles]
    check = all(role not in author_roles for role in role_ids)
    log.trace(f"{ctx.author} tried to call the '{ctx.command.name}' command. "
              f"The result of the without_role check was {check}.")
    return check


def in_channel_check(ctx: Context, channel_id: int) -> bool:
    """Checks if the command was executed inside of the specified channel."""
    check = ctx.channel.id == channel_id
    log.trace(f"{ctx.author} tried to call the '{ctx.command.name}' command. "
              f"The result of the in_channel check was {check}.")
    return check


def cooldown_with_role_bypass(rate: int, per: float, type: BucketType = BucketType.default, *,
                              bypass_roles: Iterable[int]) -> Callable:
    """
    Applies a cooldown to a command, but allows members with certain roles to be ignored.

    NOTE: this replaces the `Command.before_invoke` callback, which *might* introduce problems in the future.
    """
    # make it a set so lookup is hash based
    bypass = set(bypass_roles)

    # this handles the actual cooldown logic
    buckets = CooldownMapping(Cooldown(rate, per, type))

    # will be called after the command has been parse but before it has been invoked, ensures that
    # the cooldown won't be updated if the user screws up their input to the command
    async def predicate(cog: Cog, ctx: Context) -> None:
        nonlocal bypass, buckets

        if any(role.id in bypass for role in ctx.author.roles):
            return

        # cooldown logic, taken from discord.py internals
        current = ctx.message.created_at.replace(tzinfo=datetime.timezone.utc).timestamp()
        bucket = buckets.get_bucket(ctx.message)
        retry_after = bucket.update_rate_limit(current)
        if retry_after:
            raise CommandOnCooldown(bucket, retry_after)

    def wrapper(command: Command) -> Command:
        # NOTE: this could be changed if a subclass of Command were to be used. I didn't see the need for it
        # so I just made it raise an error when the decorator is applied before the actual command object exists.
        #
        # if the `before_invoke` detail is ever a problem then I can quickly just swap over.
        if not isinstance(command, Command):
            raise TypeError('Decorator `cooldown_with_role_bypass` must be applied after the command decorator. '
                            'This means it has to be above the command decorator in the code.')

        command._before_invoke = predicate

        return command

    return wrapper
