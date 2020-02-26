import contextlib
import logging

from discord.ext.commands import (
    BadArgument,
    BotMissingPermissions,
    CheckFailure,
    CommandError,
    CommandInvokeError,
    CommandNotFound,
    CommandOnCooldown,
    DisabledCommand,
    MissingPermissions,
    NoPrivateMessage,
    UserInputError,
)
from discord.ext.commands import Cog, Context
from sentry_sdk import push_scope

from bot.api import ResponseCodeError
from bot.bot import Bot
from bot.constants import Channels
from bot.converters import TagNameConverter
from bot.decorators import InChannelCheckFailure

log = logging.getLogger(__name__)


class ErrorHandler(Cog):
    """Handles errors emitted from commands."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @Cog.listener()
    async def on_command_error(self, ctx: Context, e: CommandError) -> None:
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
        parent = None

        if command is not None:
            parent = command.parent

        # Retrieve the help command for the invoked command.
        if parent and command:
            help_command = (self.bot.get_command("help"), parent.name, command.name)
        elif command:
            help_command = (self.bot.get_command("help"), command.name)
        else:
            help_command = (self.bot.get_command("help"),)

        if hasattr(e, "handled"):
            log.trace(f"Command {command} had its error already handled locally; ignoring.")
            return

        # Try to look for a tag with the command's name if the command isn't found.
        if isinstance(e, CommandNotFound) and not hasattr(ctx, "invoked_from_error_handler"):
            if not ctx.channel.id == Channels.verification:
                tags_get_command = self.bot.get_command("tags get")
                ctx.invoked_from_error_handler = True

                log_msg = "Cancelling attempt to fall back to a tag due to failed checks."
                try:
                    if not await tags_get_command.can_run(ctx):
                        log.debug(log_msg)
                        return
                except CommandError as tag_error:
                    log.debug(log_msg)
                    await self.on_command_error(ctx, tag_error)
                    return

                # Return to not raise the exception
                with contextlib.suppress(BadArgument, ResponseCodeError):
                    await ctx.invoke(
                        tags_get_command,
                        tag_name=await TagNameConverter.convert(ctx, ctx.invoked_with)
                    )
                    return
        elif isinstance(e, BadArgument):
            await ctx.send(f"Bad argument: {e}\n")
            await ctx.invoke(*help_command)
        elif isinstance(e, UserInputError):
            await ctx.send("Something about your input seems off. Check the arguments:")
            await ctx.invoke(*help_command)
            log.debug(
                f"Command {command} invoked by {ctx.message.author} with error "
                f"{e.__class__.__name__}: {e}"
            )
        elif isinstance(e, NoPrivateMessage):
            await ctx.send("Sorry, this command can't be used in a private message!")
        elif isinstance(e, BotMissingPermissions):
            await ctx.send(f"Sorry, it looks like I don't have the permissions I need to do that.")
            log.warning(
                f"The bot is missing permissions to execute command {command}: {e.missing_perms}"
            )
        elif isinstance(e, MissingPermissions):
            log.debug(
                f"{ctx.message.author} is missing permissions to invoke command {command}: "
                f"{e.missing_perms}"
            )
        elif isinstance(e, InChannelCheckFailure):
            await ctx.send(e)
        elif isinstance(e, (CheckFailure, CommandOnCooldown, DisabledCommand)):
            log.debug(
                f"Command {command} invoked by {ctx.message.author} with error "
                f"{e.__class__.__name__}: {e}"
            )
        elif isinstance(e, CommandInvokeError):
            if isinstance(e.original, ResponseCodeError):
                status = e.original.response.status

                if status == 404:
                    await ctx.send("There does not seem to be anything matching your query.")
                elif status == 400:
                    content = await e.original.response.json()
                    log.debug(f"API responded with 400 for command {command}: %r.", content)
                    await ctx.send("According to the API, your request is malformed.")
                elif 500 <= status < 600:
                    await ctx.send("Sorry, there seems to be an internal issue with the API.")
                    log.warning(f"API responded with {status} for command {command}")
                else:
                    await ctx.send(f"Got an unexpected status code from the API (`{status}`).")
                    log.warning(f"Unexpected API response for command {command}: {status}")
            else:
                await self.handle_unexpected_error(ctx, e.original)
        else:
            await self.handle_unexpected_error(ctx, e)

    @staticmethod
    async def handle_unexpected_error(ctx: Context, e: CommandError) -> None:
        """Generic handler for errors without an explicit handler."""
        await ctx.send(
            f"Sorry, an unexpected error occurred. Please let us know!\n\n"
            f"```{e.__class__.__name__}: {e}```"
        )

        with push_scope() as scope:
            scope.user = {
                "id": ctx.author.id,
                "username": str(ctx.author)
            }

            scope.set_tag("command", ctx.command.qualified_name)
            scope.set_tag("message_id", ctx.message.id)
            scope.set_tag("channel_id", ctx.channel.id)

            scope.set_extra("full_message", ctx.message.content)

            if ctx.guild is not None:
                scope.set_extra(
                    "jump_to",
                    f"https://discordapp.com/channels/{ctx.guild.id}/{ctx.channel.id}/{ctx.message.id}"
                )

            log.error(f"Error executing command invoked by {ctx.message.author}: {ctx.message.content}", exc_info=e)


def setup(bot: Bot) -> None:
    """Load the ErrorHandler cog."""
    bot.add_cog(ErrorHandler(bot))
