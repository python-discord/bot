import logging
import random
import typing
from asyncio import Lock, sleep
from contextlib import suppress
from functools import wraps
from weakref import WeakValueDictionary

from discord import Colour, Embed
from discord.errors import NotFound
from discord.ext import commands
from discord.ext.commands import CheckFailure, Context

from bot.constants import ERROR_REPLIES, RedirectOutput
from bot.utils.checks import with_role_check, without_role_check

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
    """
    Returns True if the user has any one
    of the roles in role_ids.
    """

    async def predicate(ctx: Context):
        return with_role_check(ctx, *role_ids)
    return commands.check(predicate)


def without_role(*role_ids: int):
    """
    Returns True if the user does not have any
    of the roles in role_ids.
    """

    async def predicate(ctx: Context):
        return without_role_check(ctx, *role_ids)
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
                    "You're already using this command. Please wait until it is done before you use it again."
                )
                embed.title = random.choice(ERROR_REPLIES)
                await ctx.send(embed=embed)
                return

            async with func.__locks.setdefault(ctx.author.id, Lock()):
                return await func(self, ctx, *args, **kwargs)
        return inner
    return wrap


def redirect_output(destination_channel: int, bypass_roles: typing.Container[int] = None):
    """
    Changes the channel in the context of the command to redirect the output
    to a certain channel, unless the author has a role to bypass redirection
    """

    def wrap(func):
        @wraps(func)
        async def inner(self, ctx, *args, **kwargs):
            if ctx.channel.id == destination_channel:
                log.trace(f"Command {ctx.command.name} was invoked in destination_channel, not redirecting")
                return await func(self, ctx, *args, **kwargs)

            if bypass_roles and any(role.id in bypass_roles for role in ctx.author.roles):
                log.trace(f"{ctx.author} has role to bypass output redirection")
                return await func(self, ctx, *args, **kwargs)

            redirect_channel = ctx.guild.get_channel(destination_channel)
            old_channel = ctx.channel

            log.trace(f"Redirecting output of {ctx.author}'s command '{ctx.command.name}' to {redirect_channel.name}")
            ctx.channel = redirect_channel
            await ctx.channel.send(f"Here's the output of your command, {ctx.author.mention}")
            await func(self, ctx, *args, **kwargs)

            message = await old_channel.send(
                f"Hey, {ctx.author.mention}, you can find the output of your command here: "
                f"{redirect_channel.mention}"
            )

            if RedirectOutput.delete_invocation:
                await sleep(RedirectOutput.delete_delay)

                with suppress(NotFound):
                    await message.delete()
                    log.trace("Redirect output: Deleted user redirection message")

                with suppress(NotFound):
                    await ctx.message.delete()
                    log.trace("Redirect output: Deleted invocation message")
        return inner
    return wrap
