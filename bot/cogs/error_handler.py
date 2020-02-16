import contextlib
import logging
import typing as t

from discord.ext.commands import Cog, Command, Context, errors

from bot.api import ResponseCodeError
from bot.bot import Bot
from bot.constants import Channels
from bot.decorators import InChannelCheckFailure

log = logging.getLogger(__name__)


class ErrorHandler(Cog):
    """Handles errors emitted from commands."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @Cog.listener()
    async def on_command_error(self, ctx: Context, e: errors.CommandError) -> None:
        """
        Provide generic command error handling.

        Error handling is deferred to any local error handler, if present.

        Error handling emits a single error response, prioritized as follows:
            1. If the name fails to match a command but matches a tag, the tag is invoked
            2. Send a BadArgument error message to the invoking context & invoke the command's help
            3. Send a UserInputError error message to the invoking context & invoke the command's help
            4. Send a NoPrivateMessage error message to the invoking context
            5. Send a BotMissingPermissions error message to the invoking context
            6. Log a MissingPermissions error, no message is sent
            7. Send a InChannelCheckFailure error message to the invoking context
            8. Log CheckFailure, CommandOnCooldown, and DisabledCommand errors, no message is sent
            9. For CommandInvokeErrors, response is based on the type of error:
                * 404: Error message is sent to the invoking context
                * 400: Log the resopnse JSON, no message is sent
                * 500 <= status <= 600: Error message is sent to the invoking context
            10. Otherwise, handling is deferred to `handle_unexpected_error`
        """
        command = ctx.command

        if hasattr(e, "handled"):
            log.trace(f"Command {command} had its error already handled locally; ignoring.")
            return

        # Try to look for a tag with the command's name if the command isn't found.
        if isinstance(e, errors.CommandNotFound) and not hasattr(ctx, "invoked_from_error_handler"):
            if ctx.channel.id != Channels.verification:
                await self.try_get_tag(ctx)
        elif isinstance(e, errors.UserInputError):
            await self.handle_user_input_error(ctx, e)
        elif isinstance(e, errors.CheckFailure):
            await self.handle_check_failure(ctx, e)
        elif isinstance(e, (errors.CommandOnCooldown, errors.DisabledCommand)):
            log.debug(
                f"Command {command} invoked by {ctx.message.author} with error "
                f"{e.__class__.__name__}: {e}"
            )
        elif isinstance(e, errors.CommandInvokeError):
            if isinstance(e.original, ResponseCodeError):
                await self.handle_api_error(ctx, e.original)
            else:
                await self.handle_unexpected_error(ctx, e.original)
        else:
            # MaxConcurrencyReached, ExtensionError
            await self.handle_unexpected_error(ctx, e)

    async def get_help_command(self, command: t.Optional[Command]) -> t.Tuple:
        """Return the help command invocation args to display help for `command`."""
        parent = None
        if command is not None:
            parent = command.parent

        # Retrieve the help command for the invoked command.
        if parent and command:
            return self.bot.get_command("help"), parent.name, command.name
        elif command:
            return self.bot.get_command("help"), command.name
        else:
            return self.bot.get_command("help")

    async def try_get_tag(self, ctx: Context) -> None:
        """
        Attempt to display a tag by interpreting the command name as a tag name.

        The invocation of tags get respects its checks. Any CommandErrors raised will be handled
        by `on_command_error`, but the `invoked_from_error_handler` attribute will be added to
        the context to prevent infinite recursion in the case of a CommandNotFound exception.
        """
        tags_get_command = self.bot.get_command("tags get")
        ctx.invoked_from_error_handler = True

        log_msg = "Cancelling attempt to fall back to a tag due to failed checks."
        try:
            if not await tags_get_command.can_run(ctx):
                log.debug(log_msg)
                return
        except errors.CommandError as tag_error:
            log.debug(log_msg)
            await self.on_command_error(ctx, tag_error)
            return

        # Return to not raise the exception
        with contextlib.suppress(ResponseCodeError):
            await ctx.invoke(tags_get_command, tag_name=ctx.invoked_with)
            return

    async def handle_user_input_error(self, ctx: Context, e: errors.UserInputError) -> None:
        """Handle UserInputError exceptions and its children."""
        # TODO: use ctx.send_help() once PR #519 is merged.
        help_command = await self.get_help_command(ctx.command)

        if isinstance(e, errors.MissingRequiredArgument):
            await ctx.send(f"Missing required argument `{e.param.name}`.")
            await ctx.invoke(*help_command)
        elif isinstance(e, errors.TooManyArguments):
            await ctx.send(f"Too many arguments provided.")
            await ctx.invoke(*help_command)
        elif isinstance(e, errors.BadArgument):
            await ctx.send(f"Bad argument: {e}\n")
            await ctx.invoke(*help_command)
        else:
            await ctx.send("Something about your input seems off. Check the arguments:")
            await ctx.invoke(*help_command)
            log.debug(
                f"Command {ctx.command} invoked by {ctx.message.author} with error "
                f"{e.__class__.__name__}: {e}"
            )

    @staticmethod
    async def handle_check_failure(ctx: Context, e: errors.CheckFailure) -> None:
        """Handle CheckFailure exceptions and its children."""
        command = ctx.command

        if isinstance(e, errors.NoPrivateMessage):
            await ctx.send("Sorry, this command can't be used in a private message!")
        elif isinstance(e, errors.BotMissingPermissions):
            await ctx.send(f"Sorry, it looks like I don't have the permissions I need to do that.")
            log.warning(
                f"The bot is missing permissions to execute command {command}: {e.missing_perms}"
            )
        elif isinstance(e, errors.MissingPermissions):
            log.debug(
                f"{ctx.message.author} is missing permissions to invoke command {command}: "
                f"{e.missing_perms}"
            )
        elif isinstance(e, InChannelCheckFailure):
            await ctx.send(e)
        else:
            log.debug(
                f"Command {command} invoked by {ctx.message.author} with error "
                f"{e.__class__.__name__}: {e}"
            )

    @staticmethod
    async def handle_api_error(ctx: Context, e: ResponseCodeError) -> None:
        """Handle ResponseCodeError exceptions."""
        if e.status == 404:
            await ctx.send("There does not seem to be anything matching your query.")
        elif e.status == 400:
            content = await e.response.json()
            log.debug(f"API responded with 400 for command {ctx.command}: %r.", content)
            await ctx.send("According to the API, your request is malformed.")
        elif 500 <= e.status < 600:
            await ctx.send("Sorry, there seems to be an internal issue with the API.")
            log.warning(f"API responded with {e.status} for command {ctx.command}")
        else:
            await ctx.send(f"Got an unexpected status code from the API (`{e.status}`).")
            log.warning(f"Unexpected API response for command {ctx.command}: {e.status}")

    @staticmethod
    async def handle_unexpected_error(ctx: Context, e: errors.CommandError) -> None:
        """Generic handler for errors without an explicit handler."""
        await ctx.send(
            f"Sorry, an unexpected error occurred. Please let us know!\n\n"
            f"```{e.__class__.__name__}: {e}```"
        )
        log.error(
            f"Error executing command invoked by {ctx.message.author}: {ctx.message.content}",
            exc_info=e
        )


def setup(bot: Bot) -> None:
    """Load the ErrorHandler cog."""
    bot.add_cog(ErrorHandler(bot))
