from typing import Callable

import discord
from discord import Interaction, Member, User

# Amount of seconds to confirm the operation.
DELETION_TIMEOUT = 60


class DeleteConfirmationView(discord.ui.View):
    """A view to confirm the deletion of a filter list."""

    def __init__(self, author: Member | User, callback: Callable):
        super().__init__(timeout=DELETION_TIMEOUT)
        self.author = author
        self.callback = callback

    async def interaction_check(self, interaction: Interaction) -> bool:
        """Only allow interactions from the command invoker."""
        return interaction.user.id == self.author.id

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.red, row=0)
    async def confirm(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Invoke the filter list deletion."""
        await interaction.response.edit_message(view=None)
        await self.callback()

    @discord.ui.button(label="Cancel", row=0)
    async def cancel(self, interaction: Interaction, button: discord.ui.Button) -> None:
        """Cancel the filter list deletion."""
        await interaction.response.edit_message(content="🚫 Operation canceled.", view=None)
