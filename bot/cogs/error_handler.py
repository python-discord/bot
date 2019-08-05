import logging

from discord.ext.commands import Bot, Context
from discord.ext.commands import (
    BadArgument,
    BotMissingPermissions,
    CommandError,
    CommandInvokeError,
    CommandNotFound,
    NoPrivateMessage,
    UserInputError,
)

from bot.api import ResponseCodeError


log = logging.getLogger(__name__)


class ErrorHandler:
    """Handles errors emttted from commands."""

    def __init__(self, bot: Bot):
        self.bot = bot

    async def on_command_error(self, ctx: Context, e: CommandError):
        command = ctx.command
        parent = None

        if command is not None:
            parent = command.parent

        if parent and command:
            help_command = (self.bot.get_command("help"), parent.name, command.name)
        elif command:
            help_command = (self.bot.get_command("help"), command.name)
        else:
            help_command = (self.bot.get_command("help"),)

        if hasattr(command, "on_error"):
            log.debug(f"Command {command} has a local error handler, ignoring.")
            return

        if isinstance(e, CommandNotFound) and not hasattr(ctx, "invoked_from_error_handler"):
            tags_get_command = self.bot.get_command("tags get")
            ctx.invoked_from_error_handler = True

            # Return to not raise the exception
            return await ctx.invoke(tags_get_command, tag_name=ctx.invoked_with)
        elif isinstance(e, BadArgument):
            await ctx.send(f"Bad argument: {e}\n")
            await ctx.invoke(*help_command)
        elif isinstance(e, UserInputError):
            await ctx.invoke(*help_command)
        elif isinstance(e, NoPrivateMessage):
            await ctx.send("Sorry, this command can't be used in a private message!")
        elif isinstance(e, BotMissingPermissions):
            await ctx.send(
                f"Sorry, it looks like I don't have the permissions I need to do that.\n\n"
                f"Here's what I'm missing: **{e.missing_perms}**"
            )
        elif isinstance(e, CommandInvokeError):
            if isinstance(e.original, ResponseCodeError):
                if e.original.response.status_code == 404:
                    await ctx.send("There does not seem to be anything matching your query.")
                elif e.original.response.status_code == 400:
                    await ctx.send("According to the API, your request is malformed.")
                elif 500 <= e.original.response.status_code < 600:
                    await ctx.send("Sorry, there seems to be an internal issue with the API.")
                else:
                    await ctx.send(
                        "Got an unexpected status code from the "
                        f"API (`{e.original.response.code}`)."
                    )

            else:
                await ctx.send(
                    f"Sorry, an unexpected error occurred. Please let us know!\n\n```{e}```"
                )
                raise e.original
        raise e


def setup(bot: Bot):
    bot.add_cog(ErrorHandler(bot))
    log.info("Cog loaded: Events")
