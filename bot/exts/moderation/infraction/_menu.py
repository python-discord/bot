"""The view and modal of the Infract user context menu."""

import typing as t
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import discord
from dateutil.relativedelta import relativedelta
from discord import Interaction
from discord.ext import commands
from discord.ext.commands import Context
from pydis_core.utils.interactions import ViewWithUserAndRoleCheck

from bot.converters import DurationOrExpiry, MemberOrUser
from bot.utils.context_menus import authorise_context, context_menu_error_handler

if t.TYPE_CHECKING:
    from bot.exts.moderation.infraction.infractions import Infractions

REASON_MAX_LENGTH = 1000


class Duration(Enum):
    """Whether an infraction takes a duration."""

    NONE = "none"
    OPTIONAL = "optional"
    REQUIRED = "required"


@dataclass(frozen=True)
class InfractionAction:
    """An infraction which can be chosen in the context menu, and the command which applies it."""

    label: str
    command: str
    duration: Duration = Duration.NONE


# The infractions which have a slash command, in the order they are listed in. The command is what gates the action,
# and what is run to apply it.
INFRACTION_ACTIONS = {
    "warn": InfractionAction("Warn", "warn"),
    "note": InfractionAction("Note", "note"),
    "kick": InfractionAction("Kick", "kick"),
    "timeout": InfractionAction("Timeout", "timeout", Duration.OPTIONAL),
    "ban": InfractionAction("Ban", "ban"),
    "tempban": InfractionAction("Temporary ban", "tempban", Duration.REQUIRED),
    "cleanban": InfractionAction("Ban and clean messages", "cleanban", Duration.OPTIONAL),
    "voicemute": InfractionAction("Voice mute", "voicemute"),
    "tempvoicemute": InfractionAction("Temporary voice mute", "tempvoicemute", Duration.REQUIRED),
}


class InfractionModal(discord.ui.Modal):
    """A modal asking for the reason, and the duration if the infraction takes one."""

    def __init__(self, cog: Infractions, ctx: Context, action: InfractionAction, user: MemberOrUser):
        super().__init__(title=f"{action.label}: {user.display_name}"[:45])
        self.cog = cog
        self.ctx = ctx
        self.action = action
        self.user = user

        self.duration: discord.ui.TextInput | None = None
        if action.duration is not Duration.NONE:
            self.duration = discord.ui.TextInput(
                label="Duration" if action.duration is Duration.REQUIRED else "Duration (optional)",
                placeholder="e.g. 3d1M, or an ISO 8601 timestamp",
                required=action.duration is Duration.REQUIRED,
                max_length=50,
            )
            self.add_item(self.duration)

        self.reason = discord.ui.TextInput(
            label="Reason (optional)",
            style=discord.TextStyle.long,
            required=False,
            max_length=REASON_MAX_LENGTH,
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: Interaction) -> None:
        """Apply the infraction through the same code as the command for it."""
        ctx = self.ctx
        # Respond to the modal submission rather than to the menu invocation.
        ctx.interaction = interaction

        # The menu was gated when it was invoked, but the roles of the invoker may have changed since.
        await authorise_context(ctx, self.action.command)
        command = ctx.command

        args = []
        if self.duration is not None:
            raw_duration = self.duration.value.strip()
            duration = None
            if raw_duration:
                duration = await self._convert_duration(raw_duration)
                if duration is None:
                    await interaction.response.send_message(
                        f":x: `{raw_duration}` is not a valid duration or ISO 8601 timestamp.", ephemeral=True
                    )
                    return
            args.append(duration)

        # The work is only done after this, as the response to a modal must be sent within 3 seconds.
        await ctx.defer()
        await ctx.invoke(command, self.user, *args, reason=self.reason.value.strip() or None)

    async def _convert_duration(self, argument: str) -> relativedelta | datetime | None:
        """Convert the duration the way the commands do, returning None if it is not valid."""
        # The converter of the commands is not used directly as its error needs the parameter being parsed.
        for converter in DurationOrExpiry.converters:
            try:
                return await converter().convert(self.ctx, argument)
            except commands.CommandError:
                continue
        return None

    async def on_error(self, interaction: Interaction, error: Exception) -> None:
        """Handle any exceptions in the processing of the modal."""
        await context_menu_error_handler(interaction, error)


class InfractionActionView(ViewWithUserAndRoleCheck):
    """A view to choose which infraction to apply to a user."""

    def __init__(self, cog: Infractions, ctx: Context, user: MemberOrUser):
        super().__init__(allowed_users=(ctx.author.id,), allowed_roles=(), timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.user = user

        self.select = discord.ui.Select(
            placeholder="Choose an infraction",
            options=[discord.SelectOption(label=action.label, value=key) for key, action in INFRACTION_ACTIONS.items()],
        )
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def on_select(self, interaction: Interaction) -> None:
        """Ask for the details of the chosen infraction."""
        action = INFRACTION_ACTIONS[self.select.values[0]]
        # Gate on the command of the chosen infraction before asking for anything.
        await authorise_context(self.ctx, action.command)
        await interaction.response.send_modal(InfractionModal(self.cog, self.ctx, action, self.user))

    async def on_error(self, interaction: Interaction, error: Exception, item: discord.ui.Item) -> None:
        """Handle any exceptions in the callbacks of the view."""
        await context_menu_error_handler(interaction, error)
