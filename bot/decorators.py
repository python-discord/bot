import asyncio
import functools
import types
import typing as t
from contextlib import suppress

import arrow
from discord import Member, NotFound
from discord.ext import commands
from discord.ext.commands import Cog, Context
from pydis_core.utils import scheduling

from bot.constants import Channels, DEBUG_MODE, RedirectOutput
from bot.log import get_logger
from bot.utils import function
from bot.utils.checks import ContextCheckFailure, in_whitelist_check
from bot.utils.function import command_wraps

log = get_logger(__name__)


def in_whitelist(
    *,
    channels: t.Container[int] = (),
    categories: t.Container[int] = (),
    roles: t.Container[int] = (),
    redirect: int | None = Channels.bot_commands,
    fail_silently: bool = False,
) -> t.Callable:
    """
    Check if a command was issued in a whitelisted context.

    The whitelists that can be provided are:

    - `channels`: a container with channel ids for whitelisted channels
    - `categories`: a container with category ids for whitelisted categories
    - `roles`: a container with role ids for whitelisted roles

    If the command was invoked in a context that was not whitelisted, the member is either
    redirected to the `redirect` channel that was passed (default: #bot-commands) or simply
    told that they're not allowed to use this particular command (if `None` was passed).
    """
    def predicate(ctx: Context) -> bool:
        """Check if command was issued in a whitelisted context."""
        return in_whitelist_check(ctx, channels, categories, roles, redirect, fail_silently)

    return commands.check(predicate)


class NotInBlacklistCheckFailure(ContextCheckFailure):
    """Raised when the 'not_in_blacklist' check fails."""


def not_in_blacklist(
    *,
    channels: t.Container[int] = (),
    categories: t.Container[int] = (),
    roles: t.Container[int] = (),
    override_roles: t.Container[int] = (),
    redirect: int | None = Channels.bot_commands,
    fail_silently: bool = False,
) -> t.Callable:
    """
    Check if a command was not issued in a blacklisted context.

    The blacklists that can be provided are:

    - `channels`: a container with channel ids for blacklisted channels
    - `categories`: a container with category ids for blacklisted categories
    - `roles`: a container with role ids for blacklisted roles

    If the command was invoked in a context that was blacklisted, the member is either
    redirected to the `redirect` channel that was passed (default: #bot-commands) or simply
    told that they're not allowed to use this particular command (if `None` was passed).

    The blacklist can be overridden through the roles specified in `override_roles`.
    """
    def predicate(ctx: Context) -> bool:
        """Check if command was issued in a blacklisted context."""
        not_blacklisted = not in_whitelist_check(ctx, channels, categories, roles, fail_silently=True)
        overridden = in_whitelist_check(ctx, roles=override_roles, fail_silently=True)

        success = not_blacklisted or overridden

        if not success and not fail_silently:
            raise NotInBlacklistCheckFailure(redirect)

        return success

    return commands.check(predicate)


def has_no_roles(*roles: str | int) -> t.Callable:
    """
    Returns True if the user does not have any of the roles specified.

    `roles` are the names or IDs of the disallowed roles.
    """
    async def predicate(ctx: Context) -> bool:
        try:
            await commands.has_any_role(*roles).predicate(ctx)
        except commands.MissingAnyRole:
            return True
        else:
            # This error is never shown to users, so don't bother trying to make it too pretty.
            roles_ = ", ".join(f"'{item}'" for item in roles)
            raise commands.CheckFailure(f"You have at least one of the disallowed roles: {roles_}")

    return commands.check(predicate)


def redirect_output(
    destination_channel: int,
    bypass_roles: t.Container[int] | None = None,
    channels: t.Container[int] | None = None,
    categories: t.Container[int] | None = None,
    ping_user: bool = True
) -> t.Callable:
    """
    Changes the channel in the context of the command to redirect the output to a certain channel.

    Redirect is bypassed if the author has a bypass role or if it is in a channel that can bypass redirection.

    If ping_user is False, it will not send a message in the destination channel.

    This decorator must go before (below) the `command` decorator.
    """
    def wrap(func: types.FunctionType) -> types.FunctionType:
        @command_wraps(func)
        async def inner(self: Cog, ctx: Context, *args, **kwargs) -> None:
            if ctx.channel.id == destination_channel:
                log.trace(f"Command {ctx.command} was invoked in destination_channel, not redirecting")
                await func(self, ctx, *args, **kwargs)
                return

            if bypass_roles and any(role.id in bypass_roles for role in ctx.author.roles):
                log.trace(f"{ctx.author} has role to bypass output redirection")
                await func(self, ctx, *args, **kwargs)
                return

            if channels and ctx.channel.id not in channels:
                log.trace(f"{ctx.author} used {ctx.command} in a channel that can bypass output redirection")
                await func(self, ctx, *args, **kwargs)
                return

            if categories and ctx.channel.category.id not in categories:
                log.trace(f"{ctx.author} used {ctx.command} in a category that can bypass output redirection")
                await func(self, ctx, *args, **kwargs)
                return

            redirect_channel = ctx.guild.get_channel(destination_channel)
            old_channel = ctx.channel

            log.trace(f"Redirecting output of {ctx.author}'s command '{ctx.command.name}' to {redirect_channel.name}")
            ctx.channel = redirect_channel

            if ping_user:
                await ctx.send(f"Here's the output of your command, {ctx.author.mention}")
            scheduling.create_task(func(self, ctx, *args, **kwargs))

            message = await old_channel.send(
                f"Hey, {ctx.author.mention}, you can find the output of your command here: "
                f"{redirect_channel.mention}"
            )
            if RedirectOutput.delete_invocation:
                await asyncio.sleep(RedirectOutput.delete_delay)

                with suppress(NotFound):
                    await message.delete()
                    log.trace("Redirect output: Deleted user redirection message")

                with suppress(NotFound):
                    await ctx.message.delete()
                    log.trace("Redirect output: Deleted invocation message")
        return inner
    return wrap


def respect_role_hierarchy(member_arg: function.Argument) -> t.Callable:
    """
    Ensure the highest role of the invoking member is greater than that of the target member.

    If the condition fails, a warning is sent to the invoking context. A target which is not an
    instance of discord.Member will always pass.

    `member_arg` is the keyword name or position index of the parameter of the decorated command
    whose value is the target member.

    This decorator must go before (below) the `command` decorator.
    """
    def decorator(func: types.FunctionType) -> types.FunctionType:
        @command_wraps(func)
        async def wrapper(*args, **kwargs) -> t.Any:
            log.trace(f"{func.__name__}: respect role hierarchy decorator called")

            bound_args = function.get_bound_args(func, args, kwargs)
            target = function.get_arg_value(member_arg, bound_args)

            if not isinstance(target, Member):
                log.trace("The target is not a discord.Member; skipping role hierarchy check.")
                return await func(*args, **kwargs)

            ctx = function.get_arg_value(1, bound_args)
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
                return None

            log.trace(f"{func.__name__}: {target.top_role=} < {actor.top_role=}; calling func")
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def mock_in_debug(return_value: t.Any) -> t.Callable:
    """
    Short-circuit function execution if in debug mode and return `return_value`.

    The original function name, and the incoming args and kwargs are DEBUG level logged
    upon each call. This is useful for expensive operations, i.e. media asset uploads
    that are prone to rate-limits but need to be tested extensively.
    """
    def decorator(func: t.Callable) -> t.Callable:
        @functools.wraps(func)
        async def wrapped(*args, **kwargs) -> t.Any:
            """Short-circuit and log if in debug mode."""
            if DEBUG_MODE:
                log.debug(f"Function {func.__name__} called with args: {args}, kwargs: {kwargs}")
                return return_value
            return await func(*args, **kwargs)
        return wrapped
    return decorator


def ensure_future_timestamp(timestamp_arg: function.Argument) -> t.Callable:
    """
    Ensure the timestamp argument is in the future.

    If the condition fails, send a warning to the invoking context.

    `timestamp_arg` is the keyword name or position index of the parameter of the decorated command
    whose value is the target timestamp.

    This decorator must go before (below) the `command` decorator.
    """
    def decorator(func: types.FunctionType) -> types.FunctionType:
        @command_wraps(func)
        async def wrapper(*args, **kwargs) -> t.Any:
            bound_args = function.get_bound_args(func, args, kwargs)
            target = function.get_arg_value(timestamp_arg, bound_args)

            ctx = function.get_arg_value(1, bound_args)

            try:
                is_future = target > arrow.utcnow()
            except TypeError:
                is_future = True
            if not is_future:
                await ctx.send(":x: Provided timestamp is in the past.")
                return None

            return await func(*args, **kwargs)
        return wrapper
    return decorator
