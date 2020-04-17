import contextlib
import logging
import typing as t

from discord.ext.commands import Cog, Command, Context, errors
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
    async def on_command_error(self, ctx: Context, e: errors.CommandError) -> None:
        """
        Provide generic command error handling.

        Error handling is deferred to any local error handler, if present. This is done by
        checking for the presence of a `handled` attribute on the error.

        Error handling emits a single error message in the invoking context `ctx` and a log message,
        prioritised as follows:

        1. If the name fails to match a command:
            * If it matches shh+ or unshh+, the channel is silenced or unsilenced respectively.
              Otherwise if it matches a tag, the tag is invoked
            * If CommandNotFound is raised when invoking the tag (determined by the presence of the
              `invoked_from_error_handler` attribute), this error is treated as being unexpected
              and therefore sends an error message
            * Commands in the verification channel are ignored
        2. UserInputError: see `handle_user_input_error`
        3. CheckFailure: see `handle_check_failure`
        4. CommandOnCooldown: send an error message in the invoking context
        5. ResponseCodeError: see `handle_api_error`
        6. Otherwise, if not a DisabledCommand, handling is deferred to `handle_unexpected_error`
        """
        command = ctx.command

        if hasattr(e, "handled"):
            log.trace(f"Command {command} had its error already handled locally; ignoring.")
            return

        if isinstance(e, errors.CommandNotFound) and not hasattr(ctx, "invoked_from_error_handler"):
            if await self.try_silence(ctx):
                return
            if ctx.channel.id != Channels.verification:
                # Try to look for a tag with the command's name
                await self.try_get_tag(ctx)
                return  # Exit early to avoid logging.
        elif isinstance(e, errors.UserInputError):
            await self.handle_user_input_error(ctx, e)
        elif isinstance(e, errors.CheckFailure):
            await self.handle_check_failure(ctx, e)
        elif isinstance(e, errors.CommandOnCooldown):
            await ctx.send(e)
        elif isinstance(e, errors.CommandInvokeError):
            if isinstance(e.original, ResponseCodeError):
                await self.handle_api_error(ctx, e.original)
            else:
                await self.handle_unexpected_error(ctx, e.original)
            return  # Exit early to avoid logging.
        elif not isinstance(e, errors.DisabledCommand):
            # ConversionError, MaxConcurrencyReached, ExtensionError
            await self.handle_unexpected_error(ctx, e)
            return  # Exit early to avoid logging.

        log.debug(
            f"Command {command} invoked by {ctx.message.author} with error "
            f"{e.__class__.__name__}: {e}"
        )

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

    async def try_silence(self, ctx: Context) -> bool:
        """
        Attempt to invoke the silence or unsilence command if invoke with matches a pattern.

        Respecting the checks if:
        * invoked with `shh+` silence channel for amount of h's*2 with max of 15.
        * invoked with `unshh+` unsilence channel
        Return bool depending on success of command.
        """
        command = ctx.invoked_with.lower()
        silence_command = self.bot.get_command("silence")
        ctx.invoked_from_error_handler = True
        try:
            if not await silence_command.can_run(ctx):
                log.debug("Cancelling attempt to invoke silence/unsilence due to failed checks.")
                return False
        except errors.CommandError:
            log.debug("Cancelling attempt to invoke silence/unsilence due to failed checks.")
            return False
        if command.startswith("shh"):
            await ctx.invoke(silence_command, duration=min(command.count("h")*2, 15))
            return True
        elif command.startswith("unshh"):
            await ctx.invoke(self.bot.get_command("unsilence"))
            return True
        return False

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

        try:
            tag_name = await TagNameConverter.convert(ctx, ctx.invoked_with)
        except errors.BadArgument:
            log.debug(
                f"{ctx.author} tried to use an invalid command "
                f"and the fallback tag failed validation in TagNameConverter."
            )
        else:
            with contextlib.suppress(ResponseCodeError):
                await ctx.invoke(tags_get_command, tag_name=tag_name)
        # Return to not raise the exception
        return

    async def handle_user_input_error(self, ctx: Context, e: errors.UserInputError) -> None:
        """
        Send an error message in `ctx` for UserInputError, sometimes invoking the help command too.

        * MissingRequiredArgument: send an error message with arg name and the help command
        * TooManyArguments: send an error message and the help command
        * BadArgument: send an error message and the help command
        * BadUnionArgument: send an error message including the error produced by the last converter
        * ArgumentParsingError: send an error message
        * Other: send an error message and the help command
        """
        # TODO: use ctx.send_help() once PR #519 is merged.
        help_command = await self.get_help_command(ctx.command)

        if isinstance(e, errors.MissingRequiredArgument):
            await ctx.send(f"Missing required argument `{e.param.name}`.")
            await ctx.invoke(*help_command)
            self.bot.stats.incr("errors.missing_required_argument")
        elif isinstance(e, errors.TooManyArguments):
            await ctx.send(f"Too many arguments provided.")
            await ctx.invoke(*help_command)
            self.bot.stats.incr("errors.too_many_arguments")
        elif isinstance(e, errors.BadArgument):
            await ctx.send(f"Bad argument: {e}\n")
            await ctx.invoke(*help_command)
            self.bot.stats.incr("errors.bad_argument")
        elif isinstance(e, errors.BadUnionArgument):
            await ctx.send(f"Bad argument: {e}\n```{e.errors[-1]}```")
            self.bot.stats.incr("errors.bad_union_argument")
        elif isinstance(e, errors.ArgumentParsingError):
            await ctx.send(f"Argument parsing error: {e}")
            self.bot.stats.incr("errors.argument_parsing_error")
        else:
            await ctx.send("Something about your input seems off. Check the arguments:")
            await ctx.invoke(*help_command)
            self.bot.stats.incr("errors.other_user_input_error")

    @staticmethod
    async def handle_check_failure(ctx: Context, e: errors.CheckFailure) -> None:
        """
        Send an error message in `ctx` for certain types of CheckFailure.

        The following types are handled:

        * BotMissingPermissions
        * BotMissingRole
        * BotMissingAnyRole
        * NoPrivateMessage
        * InChannelCheckFailure
        """
        bot_missing_errors = (
            errors.BotMissingPermissions,
            errors.BotMissingRole,
            errors.BotMissingAnyRole
        )

        if isinstance(e, bot_missing_errors):
            ctx.bot.stats.incr("errors.bot_permission_error")
            await ctx.send(
                f"Sorry, it looks like I don't have the permissions or roles I need to do that."
            )
        elif isinstance(e, (InChannelCheckFailure, errors.NoPrivateMessage)):
            ctx.bot.stats.incr("errors.wrong_channel_or_dm_error")
            await ctx.send(e)

    @staticmethod
    async def handle_api_error(ctx: Context, e: ResponseCodeError) -> None:
        """Send an error message in `ctx` for ResponseCodeError and log it."""
        if e.status == 404:
            await ctx.send("There does not seem to be anything matching your query.")
            log.debug(f"API responded with 404 for command {ctx.command}")
            ctx.bot.stats.incr("errors.api_error_404")
        elif e.status == 400:
            content = await e.response.json()
            log.debug(f"API responded with 400 for command {ctx.command}: %r.", content)
            await ctx.send("According to the API, your request is malformed.")
            ctx.bot.stats.incr("errors.api_error_400")
        elif 500 <= e.status < 600:
            await ctx.send("Sorry, there seems to be an internal issue with the API.")
            log.warning(f"API responded with {e.status} for command {ctx.command}")
            ctx.bot.stats.incr("errors.api_internal_server_error")
        else:
            await ctx.send(f"Got an unexpected status code from the API (`{e.status}`).")
            log.warning(f"Unexpected API response for command {ctx.command}: {e.status}")
            ctx.bot.stats.incr(f"errors.api_error_{e.status}")

    @staticmethod
    async def handle_unexpected_error(ctx: Context, e: errors.CommandError) -> None:
        """Send a generic error message in `ctx` and log the exception as an error with exc_info."""
        await ctx.send(
            f"Sorry, an unexpected error occurred. Please let us know!\n\n"
            f"```{e.__class__.__name__}: {e}```"
        )

        ctx.bot.stats.incr("errors.unexpected")

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
