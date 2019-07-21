import logging

from discord.ext.commands import Context

log = logging.getLogger(__name__)


def with_role_check(ctx: Context, *role_ids: int) -> bool:
    """
    Returns True if the user has any one
    of the roles in role_ids.
    """

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
    """
    Returns True if the user does not have any
    of the roles in role_ids.
    """

    if not ctx.guild:  # Return False in a DM
        log.trace(f"{ctx.author} tried to use the '{ctx.command.name}' command from a DM. "
                  "This command is restricted by the without_role decorator. Rejecting request.")
        return False

    author_roles = (role.id for role in ctx.author.roles)
    check = all(role not in author_roles for role in role_ids)
    log.trace(f"{ctx.author} tried to call the '{ctx.command.name}' command. "
              f"The result of the without_role check was {check}.")
    return check


def in_channel_check(ctx: Context, channel_id: int) -> bool:
    """
    Checks if the command was executed
    inside of the specified channel.
    """

    check = ctx.channel.id == channel_id
    log.trace(f"{ctx.author} tried to call the '{ctx.command.name}' command. "
              f"The result of the in_channel check was {check}.")
    return check
