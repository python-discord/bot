from copy import copy

import discord
import discord.ui
from discord.ext.commands import Context

import bot
from bot.log import get_logger

log = get_logger(__name__)


class ArgumentCompletionSelect(discord.ui.Select):
    """A select detailing the options that can be picked to assign to a missing argument."""

    def __init__(self, ctx: Context, arg_name: str, options: list[str]):
        super().__init__(
            placeholder=f"Select a value for {arg_name!r}",
            options=[discord.SelectOption(label=option) for option in options]
        )
        self.ctx = ctx

    async def callback(self, interaction: discord.Interaction) -> None:
        """re-invoke the context command with the completed argument value."""
        await interaction.response.defer()
        value = interaction.data['values'][0]
        message = copy(self.ctx.message)
        message.content = f'{message.content} "{value}"'
        log.trace(f"Argument filled with the value {value}. Invoking {message.content!r}")
        await bot.instance.process_commands(message)


class ArgumentCompletionView(discord.ui.View):
    """A view used to complete a missing argument in an in invoked command."""

    def __init__(self, ctx: Context, arg_name: str, options: list[str]):
        super().__init__()
        log.trace(f"The {arg_name} argument was designated missing in the invocation {ctx.view.buffer!r}")
        self.add_item(ArgumentCompletionSelect(ctx, arg_name, options))
        self.ctx = ctx

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check to ensure that the interacting user is the user who invoked the command."""
        if interaction.user != self.ctx.author:
            embed = discord.Embed(description="Sorry, but this dropdown menu can only be used by the original author.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True
