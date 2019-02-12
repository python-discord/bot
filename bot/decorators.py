import logging
import random
import typing
from asyncio import Lock
from functools import wraps
from weakref import WeakValueDictionary

from discord import Colour, Embed
from discord.ext import commands
from discord.ext.commands import CheckFailure, Context

from bot.constants import ERROR_REPLIES

log = logging.getLogger(__name__)


class InChannelCheckFailure(CheckFailure):
    pass


def in_channel(*channels: int, bypass_roles: typing.Container[int] = None):
    """
    Checks that the message is in a whitelisted channel or optionally has a bypass role.
    """
    def predicate(ctx: Context):
        if ctx.channel.id in channels:
            log.debug(f"{ctx.author} tried to call the '{ctx.command.name}' command. "
                      f"The command was used in a whitelisted channel.")
            return True

        if bypass_roles:
            if any(r.id in bypass_roles for r in ctx.author.roles):
                log.debug(f"{ctx.author} tried to call the '{ctx.command.name}' command. "
                          f"The command was not used in a whitelisted channel, "
                          f"but the author had a role to bypass the in_channel check.")
                return True

        log.debug(f"{ctx.author} tried to call the '{ctx.command.name}' command. "
                  f"The in_channel check failed.")

        channels_str = ', '.join(f"<#{c_id}>" for c_id in channels)
        raise InChannelCheckFailure(
            f"Sorry, but you may only use this command within {channels_str}."
        )

    return commands.check(predicate)


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
            log.debug(
                f"{ctx.author} tried to use the '{ctx.command.name}' command from a DM. "
                "This command is restricted by the without_role decorator. Rejecting request."
            )
            return False

        author_roles = [role.id for role in ctx.author.roles]
        check = all(role not in author_roles for role in role_ids)
        log.debug(f"{ctx.author} tried to call the '{ctx.command.name}' command. "
                  f"The result of the without_role check was {check}.")
        return check
    return commands.check(predicate)


def locked():
    """
    Allows the user to only run one instance of the decorated command at a time.
    Subsequent calls to the command from the same author are
    ignored until the command has completed invocation.

    This decorator has to go before (below) the `command` decorator.
    """

    def wrap(func):
        func.__locks = WeakValueDictionary()

        @wraps(func)
        async def inner(self, ctx, *args, **kwargs):
            lock = func.__locks.setdefault(ctx.author.id, Lock())
            if lock.locked():
                embed = Embed()
                embed.colour = Colour.red()

                log.debug(f"User tried to invoke a locked command.")
                embed.description = (
                    "You're already using this command. "
                    "Please wait until it is done before you use it again."
                )
                embed.title = random.choice(ERROR_REPLIES)
                await ctx.send(embed=embed)
                return

            async with func.__locks.setdefault(ctx.author.id, Lock()):
                return await func(self, ctx, *args, **kwargs)
        return inner
    return wrap
