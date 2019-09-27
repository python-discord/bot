import logging
import random
from asyncio import Lock, sleep
from contextlib import suppress
from functools import wraps
from typing import Any, Callable, Container, Optional, Union
from weakref import WeakValueDictionary

from discord import Colour, Embed, Member
from discord.errors import NotFound
from discord.ext import commands
from discord.ext.commands import CheckFailure, Context

from bot.constants import ERROR_REPLIES, RedirectOutput
from bot.utils.checks import with_role_check, without_role_check

log = logging.getLogger(__name__)


class InChannelCheckFailure(CheckFailure):
    """Raised when a check fails for a message being sent in a whitelisted channel."""

    def __init__(self, *channels: int):
        self.channels = channels
        channels_str = ', '.join(f"<#{c_id}>" for c_id in channels)

        super().__init__(f"Sorry, but you may only use this command within {channels_str}.")


def in_channel(*channels: int, bypass_roles: Container[int] = None) -> Callable:
    """Checks that the message is in a whitelisted channel or optionally has a bypass role."""
    def predicate(ctx: Context) -> bool:
        """In-channel checker predicate."""
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

        raise InChannelCheckFailure(*channels)

    return commands.check(predicate)


def with_role(*role_ids: int) -> Callable:
    """Returns True if the user has any one of the roles in role_ids."""
    async def predicate(ctx: Context) -> bool:
        """With role checker predicate."""
        return with_role_check(ctx, *role_ids)
    return commands.check(predicate)


def without_role(*role_ids: int) -> Callable:
    """Returns True if the user does not have any of the roles in role_ids."""
    async def predicate(ctx: Context) -> bool:
        return without_role_check(ctx, *role_ids)
    return commands.check(predicate)


def locked() -> Callable:
    """
    Allows the user to only run one instance of the decorated command at a time.

    Subsequent calls to the command from the same author are ignored until the command has completed invocation.

    This decorator must go before (below) the `command` decorator.
    """
    def wrap(func: Callable) -> Callable:
        func.__locks = WeakValueDictionary()

        @wraps(func)
        async def inner(self: Callable, ctx: Context, *args, **kwargs) -> Optional[Any]:
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


def redirect_output(destination_channel: int, bypass_roles: Container[int] = None) -> Callable:
    """
    Changes the channel in the context of the command to redirect the output to a certain channel.

    Redirect is bypassed if the author has a role to bypass redirection.

    This decorator must go before (below) the `command` decorator.
    """
    def wrap(func: Callable) -> Callable:
        @wraps(func)
        async def inner(self: Callable, ctx: Context, *args, **kwargs) -> Any:
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


def respect_role_hierarchy(target_arg: Union[int, str] = 0) -> Callable:
    """
    Ensure the highest role of the invoking member is greater than that of the target member.

    If the condition fails, a warning is sent to the invoking context. A target which is not an
    instance of discord.Member will always pass.

    A value of 0 (i.e. position 0) for `target_arg` corresponds to the argument which comes after
    `ctx`. If the target argument is a kwarg, its name can instead be given.

    This decorator must go before (below) the `command` decorator.
    """
    def wrap(func: Callable) -> Callable:
        @wraps(func)
        async def inner(self: Callable, ctx: Context, *args, **kwargs) -> Any:
            try:
                target = kwargs[target_arg]
            except KeyError:
                try:
                    target = args[target_arg]
                except IndexError:
                    log.error(f"Could not find target member argument at position {target_arg}")
                except TypeError:
                    log.error(f"Could not find target member kwarg with key {target_arg!r}")

            if not isinstance(target, Member):
                log.trace("The target is not a discord.Member; skipping role hierarchy check.")
                return await func(self, ctx, *args, **kwargs)

            cmd = ctx.command.name
            actor = ctx.author
            if target.top_role >= actor.top_role:
                log.info(
                    f"{actor} ({actor.id}) attempted to {cmd} "
                    f"{target} ({target.id}), who has an equal or higher top role."
                )
                await ctx.send(
                    f":x: {actor.mention}, you may not {cmd} "
                    "someone with an equal or higher top role."
                )
            else:
                return await func(self, ctx, *args, **kwargs)
        return inner
    return wrap
