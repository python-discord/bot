"""Helpers for context menu commands, which must enforce the same checks as the commands they mirror."""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context
from pydis_core.site_api import ResponseCodeError
from sentry_sdk import new_scope

from bot.errors import InvalidInfractedUserError, LockedResourceError
from bot.log import get_logger
from bot.utils.checks import ContextCheckFailure

log = get_logger(__name__)

DEFAULT_DENIAL = "You do not have permission to use this command here."


class ContextMenuDenied(app_commands.CheckFailure):
    """Raised when the invoker of a context menu is not allowed to use it."""

    def __init__(self, message: str = DEFAULT_DENIAL):
        self.message = message
        super().__init__(message)


async def authorise_command(interaction: discord.Interaction, command_name: str) -> Context:
    """
    Run everything that gates the text command `command_name` against the invoker of `interaction`.

    This covers the global checks, the cog check, the checks of the command and of its parent groups,
    cooldowns and the command's before invoke hook (which is where `cooldown_with_role_bypass` is applied).
    Context menus are not commands, so none of this happens automatically for them.

    Returns a context for the interaction, with its command set to `command_name`, which can be used to run the
    logic of the command. Raises `ContextMenuDenied` if the invoker is not allowed to use the command.
    """
    # For a context menu the author of this context is the user who invoked the menu.
    ctx = await interaction.client.get_context(interaction)
    await authorise_context(ctx, command_name)
    return ctx


async def authorise_context(ctx: Context, command_name: str) -> None:
    """
    Gate `ctx` on the text command `command_name`, as `authorise_command` does, and set it as the command of `ctx`.

    This is for menus which need to gate on more than one command, or when the interaction which started the
    context has been replaced by a later one, such as that of a modal.
    """
    command = ctx.bot.get_command(command_name)
    if command is None:
        raise RuntimeError(f"Command {command_name!r} does not exist, so a menu can't be gated on it.")

    ctx.command = command
    ctx.invoked_with = command.name

    try:
        for cmd in (*reversed(command.parents), command):
            # Use the base implementation of `can_run`, as a hybrid command would defer to the checks of its
            # slash command if the context has an interaction.
            if not await commands.Command.can_run(cmd, ctx):
                raise ContextMenuDenied
        command._prepare_cooldowns(ctx)
        await command.call_before_hooks(ctx)
    except commands.CommandOnCooldown as e:
        raise ContextMenuDenied(f"This command is on cooldown. Try again in {e.retry_after:.0f} seconds.") from e
    except ContextCheckFailure as e:
        raise ContextMenuDenied(str(e)) from e
    except commands.CommandError as e:
        raise ContextMenuDenied from e

    ctx.command = command


async def _respond(interaction: discord.Interaction, content: str) -> None:
    """Send `content` as an ephemeral message, whether or not the interaction has been responded to."""
    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=True)
    else:
        await interaction.response.send_message(content, ephemeral=True)


async def context_menu_error_handler(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    """Tell the invoker of a context menu why it failed, ephemerally, and log unexpected errors."""
    if isinstance(error, app_commands.CommandInvokeError):
        error = error.original

    if isinstance(error, ContextMenuDenied):
        await _respond(interaction, f":x: {error.message}")
        return

    if isinstance(error, app_commands.MissingAnyRole | app_commands.MissingRole | app_commands.NoPrivateMessage):
        await _respond(interaction, f":x: {DEFAULT_DENIAL}")
        return

    if isinstance(error, LockedResourceError):
        await _respond(interaction, f":x: {error} Please wait for it to finish and try again later.")
        return

    if isinstance(error, InvalidInfractedUserError):
        await _respond(interaction, f":x: Cannot infract that user. {error.reason}")
        return

    if isinstance(error, ResponseCodeError):
        await _respond(interaction, f":x: There was an error from the site API (status {error.status}).")
    else:
        await _respond(
            interaction,
            ":x: An unexpected error occurred. Please let us know!\n\n"
            f"```{error.__class__.__name__}: {error}```"
        )

    command_name = interaction.command.name if interaction.command else None
    with new_scope() as scope:
        scope.user = {"id": interaction.user.id, "username": str(interaction.user)}
        scope.set_tag("command", command_name)
        scope.set_extra("interaction_data", interaction.data)

        log.error(
            "Error executing context menu '%s' invoked by %s",
            command_name,
            interaction.user,
            exc_info=error,
        )
