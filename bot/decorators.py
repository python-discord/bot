import logging
import random
from asyncio import Lock, create_task, sleep
from contextlib import suppress
from functools import wraps
from typing import Callable, Container, Optional, Union
from weakref import WeakValueDictionary

from discord import Colour, Embed, Member
from discord.errors import NotFound
from discord.ext import commands
from discord.ext.commands import Cog, Context

from bot.constants import Channels, ERROR_REPLIES, RedirectOutput
from bot.utils.checks import in_whitelist_check, with_role_check, without_role_check

log = logging.getLogger(__name__)


def in_whitelist(
    *,
    channels: Container[int] = (),
    categories: Container[int] = (),
    roles: Container[int] = (),
    redirect: Optional[int] = Channels.bot_commands,
    fail_silently: bool = False,
) -> Callable:
    """
    Check if a command was issued in a whitelisted context.

    The whitelists that can be provided are:

    - `channels`: a container with channel ids for whitelisted channels
    - `categories`: a container with category ids for whitelisted categories
    - `roles`: a container with with role ids for whitelisted roles

    If the command was invoked in a context that was not whitelisted, the member is either
    redirected to the `redirect` channel that was passed (default: #bot-commands) or simply
    told that they're not allowed to use this particular command (if `None` was passed).
    """
    def predicate(ctx: Context) -> bool:
        """Check if command was issued in a whitelisted context."""
        return in_whitelist_check(ctx, channels, categories, roles, redirect, fail_silently)

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
        async def inner(self: Cog, ctx: Context, *args, **kwargs) -> None:
            lock = func.__locks.setdefault(ctx.author.id, Lock())
            if lock.locked():
                embed = Embed()
                embed.colour = Colour.red()

                log.debug("User tried to invoke a locked command.")
                embed.description = (
                    "You're already using this command. Please wait until it is done before you use it again."
                )
                embed.title = random.choice(ERROR_REPLIES)
                await ctx.send(embed=embed)
                return

            async with func.__locks.setdefault(ctx.author.id, Lock()):
                await func(self, ctx, *args, **kwargs)
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
        async def inner(self: Cog, ctx: Context, *args, **kwargs) -> None:
            if ctx.channel.id == destination_channel:
                log.trace(f"Command {ctx.command.name} was invoked in destination_channel, not redirecting")
                await func(self, ctx, *args, **kwargs)
                return

            if bypass_roles and any(role.id in bypass_roles for role in ctx.author.roles):
                log.trace(f"{ctx.author} has role to bypass output redirection")
                await func(self, ctx, *args, **kwargs)
                return

            redirect_channel = ctx.guild.get_channel(destination_channel)
            old_channel = ctx.channel

            log.trace(f"Redirecting output of {ctx.author}'s command '{ctx.command.name}' to {redirect_channel.name}")
            ctx.channel = redirect_channel
            await ctx.channel.send(f"Here's the output of your command, {ctx.author.mention}")
            create_task(func(self, ctx, *args, **kwargs))

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
        async def inner(self: Cog, ctx: Context, *args, **kwargs) -> None:
            try:
                target = kwargs[target_arg]
            except KeyError:
                try:
                    target = args[target_arg]
                except IndexError:
                    raise ValueError(f"Could not find target argument at position {target_arg}")
                except TypeError:
                    raise ValueError(f"Could not find target kwarg with key {target_arg!r}")

            if not isinstance(target, Member):
                log.trace("The target is not a discord.Member; skipping role hierarchy check.")
                await func(self, ctx, *args, **kwargs)
                return

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
                await func(self, ctx, *args, **kwargs)
        return inner
    return wrap
