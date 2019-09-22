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
from discord.ext.commands import Bot, Cog, Context

from bot.api import ResponseCodeError
from bot.constants import Channels
from bot.decorators import InChannelCheckFailure

log = logging.getLogger(__name__)


class ErrorHandler(Cog):
    """Handles errors emitted from commands."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @Cog.listener()
    async def on_command_error(self, ctx: Context, e: CommandError):
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

                # Return to not raise the exception
                with contextlib.suppress(ResponseCodeError):
                    return await ctx.invoke(tags_get_command, tag_name=ctx.invoked_with)
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
    async def handle_unexpected_error(ctx: Context, e: CommandError):
        await ctx.send(
            f"Sorry, an unexpected error occurred. Please let us know!\n\n"
            f"```{e.__class__.__name__}: {e}```"
        )
        log.error(
            f"Error executing command invoked by {ctx.message.author}: {ctx.message.content}"
        )
        raise e


def setup(bot: Bot):
    bot.add_cog(ErrorHandler(bot))
    log.info("Cog loaded: Events")
