from collections.abc import Callable, Container, Iterable

from discord.ext.commands import (
    BucketType,
    CheckFailure,
    Cog,
    Command,
    CommandOnCooldown,
    Context,
    Cooldown,
    CooldownMapping,
    NoPrivateMessage,
    has_any_role,
)

from bot import constants
from bot.log import get_logger

log = get_logger(__name__)


class ContextCheckFailure(CheckFailure):
    """Raised when a context-specific check fails."""

    def __init__(self, redirect_channel: int | None) -> None:
        self.redirect_channel = redirect_channel

        if redirect_channel:
            redirect_message = f" here. Please use the <#{redirect_channel}> channel instead"
        else:
            redirect_message = ""

        error_message = f"You are not allowed to use that command{redirect_message}."

        super().__init__(error_message)


class InWhitelistCheckFailure(ContextCheckFailure):
    """Raised when the `in_whitelist` check fails."""


def in_whitelist_check(
    ctx: Context,
    channels: Container[int] = (),
    categories: Container[int] = (),
    roles: Container[int] = (),
    redirect: int | None = constants.Channels.bot_commands,
    fail_silently: bool = False,
) -> bool:
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
    if redirect and redirect not in channels:
        # It does not make sense for the channel whitelist to not contain the redirection
        # channel (if applicable). That's why we add the redirection channel to the `channels`
        # container if it's not already in it. As we allow any container type to be passed,
        # we first create a tuple in order to safely add the redirection channel.
        #
        # Note: It's possible for the redirect channel to be in a whitelisted category, but
        # there's no easy way to check that and as a channel can easily be moved in and out of
        # categories, it's probably not wise to rely on its category in any case.
        channels = tuple(channels) + (redirect,)

    if channels and ctx.channel.id in channels:
        log.trace(f"{ctx.author} may use the `{ctx.command.name}` command as they are in a whitelisted channel.")
        return True

    # Only check the category id if we have a category whitelist and the channel has a `category_id`
    if categories and hasattr(ctx.channel, "category_id") and ctx.channel.category_id in categories:
        log.trace(f"{ctx.author} may use the `{ctx.command.name}` command as they are in a whitelisted category.")
        return True

    # Only check the roles whitelist if we have one and ensure the author's roles attribute returns
    # an iterable to prevent breakage in DM channels (for if we ever decide to enable commands there).
    if roles and any(r.id in roles for r in getattr(ctx.author, "roles", ())):
        log.trace(f"{ctx.author} may use the `{ctx.command.name}` command as they have a whitelisted role.")
        return True

    log.trace(f"{ctx.author} may not use the `{ctx.command.name}` command within this context.")

    # Some commands are secret, and should produce no feedback at all.
    if not fail_silently:
        raise InWhitelistCheckFailure(redirect)
    return False


async def has_any_role_check(ctx: Context, *roles: str | int) -> bool:
    """
    Returns True if the context's author has any of the specified roles.

    `roles` are the names or IDs of the roles for which to check.
    False is always returns if the context is outside a guild.
    """
    try:
        return await has_any_role(*roles).predicate(ctx)
    except CheckFailure:
        return False


async def has_no_roles_check(ctx: Context, *roles: str | int) -> bool:
    """
    Returns True if the context's author doesn't have any of the specified roles.

    `roles` are the names or IDs of the roles for which to check.
    False is always returns if the context is outside a guild.
    """
    try:
        return not await has_any_role(*roles).predicate(ctx)
    except NoPrivateMessage:
        return False
    except CheckFailure:
        return True


def cooldown_with_role_bypass(
    rate: int,
    per: float,
    type: BucketType = BucketType.default,
    *,
    bypass_roles: Iterable[int]
) -> Callable:
    """
    Applies a cooldown to a command, but allows members with certain roles to be ignored.

    NOTE: this replaces the `Command.before_invoke` callback, which *might* introduce problems in the future.
    """
    # make it a set so lookup is hash based
    bypass = set(bypass_roles)

    # this handles the actual cooldown logic
    buckets = CooldownMapping(Cooldown(rate, per), type)

    # will be called after the command has been parse but before it has been invoked, ensures that
    # the cooldown won't be updated if the user screws up their input to the command
    async def predicate(cog: Cog, ctx: Context) -> None:
        nonlocal bypass, buckets

        if any(role.id in bypass for role in ctx.author.roles):
            return

        # cooldown logic, taken from discord.py internals
        current = ctx.message.created_at.timestamp()
        bucket = buckets.get_bucket(ctx.message)
        retry_after = bucket.update_rate_limit(current)
        if retry_after:
            raise CommandOnCooldown(bucket, retry_after, type)

    def wrapper(command: Command) -> Command:
        # NOTE: this could be changed if a subclass of Command were to be used. I didn't see the need for it
        # so I just made it raise an error when the decorator is applied before the actual command object exists.
        #
        # if the `before_invoke` detail is ever a problem then I can quickly just swap over.
        if not isinstance(command, Command):
            raise TypeError(
                "Decorator `cooldown_with_role_bypass` must be applied after the command decorator. "
                "This means it has to be above the command decorator in the code."
            )

        command._before_invoke = predicate

        return command

    return wrapper
