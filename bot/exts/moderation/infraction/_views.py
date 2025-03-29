from typing import Any

import discord
from discord import ButtonStyle, Interaction
from discord.ui import Button
from pydis_core.utils import interactions


class BanConfirmationView(interactions.ViewWithUserAndRoleCheck):
    """A confirmation view to be sent before issuing potentially suspect infractions."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.confirmed = False

    @discord.ui.button(label="Ban", style=ButtonStyle.red)
    async def confirm(self, interaction: Interaction, button: Button) -> None:
        """Callback coroutine that is called when the "Ban" button is pressed."""
        self.confirmed = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Cancel", style=ButtonStyle.gray)
    async def cancel(self, interaction: Interaction, button: Button) -> None:
        """Callback coroutine that is called when the "cancel" button is pressed."""
        await interaction.response.send_message("Cancelled infraction.")
        self.stop()

    async def on_timeout(self) -> None:
        await super().on_timeout()
        await self.message.reply("Cancelled infraction due to timeout.")
