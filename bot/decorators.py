import asyncio
import logging
import typing as t
from contextlib import suppress
from functools import wraps

from discord import Member, NotFound
from discord.ext import commands
from discord.ext.commands import Cog, Context

from bot.constants import Channels, RedirectOutput
from bot.utils import function
from bot.utils.checks import in_whitelist_check

log = logging.getLogger(__name__)


def in_whitelist(
    *,
    channels: t.Container[int] = (),
    categories: t.Container[int] = (),
    roles: t.Container[int] = (),
    redirect: t.Optional[int] = Channels.bot_commands,
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


def has_no_roles(*roles: t.Union[str, int]) -> t.Callable:
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


def redirect_output(destination_channel: int, bypass_roles: t.Container[int] = None) -> t.Callable:
    """
    Changes the channel in the context of the command to redirect the output to a certain channel.

    Redirect is bypassed if the author has a role to bypass redirection.

    This decorator must go before (below) the `command` decorator.
    """
    def wrap(func: t.Callable) -> t.Callable:
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
            asyncio.create_task(func(self, ctx, *args, **kwargs))

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
    def decorator(func: t.Callable) -> t.Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> None:
            log.trace(f"{func.__name__}: respect role hierarchy decorator called")

            bound_args = function.get_bound_args(func, args, kwargs)
            target = function.get_arg_value(member_arg, bound_args)

            if not isinstance(target, Member):
                log.trace("The target is not a discord.Member; skipping role hierarchy check.")
                await func(*args, **kwargs)
                return

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
            else:
                log.trace(f"{func.__name__}: {target.top_role=} < {actor.top_role=}; calling func")
                await func(*args, **kwargs)
        return wrapper
    return decorator
