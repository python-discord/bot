# coding=utf-8
import logging

from discord.ext import commands
from discord.ext.commands import Context

log = logging.getLogger(__name__)


def with_role(*role_ids: int):
    async def predicate(ctx: Context):
        if not ctx.guild:  # Return False in a DM
            log.debug(f"{ctx.author} tried to use the '{ctx.command.name}'command from a DM. "
                      "This command is restricted by the with_role decorator. Rejecting request.")
            return False

        for role in ctx.author.roles:
            if role.id in role_ids:
                log.debug(f"{ctx.author} has the '{role.name}' role, and passes the check.")
                return True

        log.debug(f"{ctx.author} does not have the required role to use "
                  f"the '{ctx.command.name}' command, so the request is rejected.")
        return False
    return commands.check(predicate)


def without_role(*role_ids: int):
    async def predicate(ctx: Context):
        if not ctx.guild:  # Return False in a DM
            log.debug(f"{ctx.author} tried to use the '{ctx.command.name}' command from a DM. "
                      "This command is restricted by the without_role decorator. Rejecting request.")
            return False

        author_roles = [role.id for role in ctx.author.roles]
        check = all(role not in author_roles for role in role_ids)
        log.debug(f"{ctx.author} tried to call the '{ctx.command.name}' command. "
                  f"The result of the without_role check was {check}.")
        return check
    return commands.check(predicate)


def in_channel(channel_id):
    async def predicate(ctx: Context):
        check = ctx.channel.id == channel_id
        log.debug(f"{ctx.author} tried to call the '{ctx.command.name}' command. "
                  f"The result of the in_channel check was {check}.")
        return check
    return commands.check(predicate)
