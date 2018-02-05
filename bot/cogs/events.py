# coding=utf-8
from discord import Guild
from discord.ext.commands import (
    AutoShardedBot, CommandError, Context, BadArgument, NoPrivateMessage,
    CommandInvokeError, UserInputError, BotMissingPermissions
)

__author__ = "Gareth Coles"


class Events:
    """
    No commands, just event handlers
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    async def on_command_error(self, ctx: Context, e: CommandError):
        command = ctx.command
        parent = command.parent

        if parent:
            help_command = (self.bot.get_command("help"), parent.name, command.name)
        else:
            help_command = (self.bot.get_command("help"), command.name)

        if isinstance(e, BadArgument):
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
            await ctx.send(
                f"Sorry, an unexpected error occurred. Please let us know!\n\n```{e}```"
            )
            raise e.original
        print(e)


def setup(bot):
    bot.add_cog(Events(bot))
    print("Cog loaded: Events")
