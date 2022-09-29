from datetime import timedelta
from enum import Enum, auto
from typing import ClassVar

import arrow
from discord import Colour, Embed
from discord.errors import Forbidden
from pydantic import validator

import bot
from bot.constants import Channels, Guild
from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings_types.settings_entry import ActionEntry


class Infraction(Enum):
    """An enumeration of infraction types. The lower the value, the higher it is on the hierarchy."""

    BAN = auto()
    KICK = auto()
    MUTE = auto()
    VOICE_BAN = auto()
    SUPERSTAR = auto()
    WARNING = auto()
    WATCH = auto()
    NOTE = auto()

    def __str__(self) -> str:
        return self.name


class InfractionAndNotification(ActionEntry):
    """
    A setting entry which specifies what infraction to issue and the notification to DM the user.

    Since a DM cannot be sent when a user is banned or kicked, these two functions need to be grouped together.
    """

    name: ClassVar[str] = "infraction_and_notification"
    description: ClassVar[dict[str, str]] = {
        "infraction_type": (
            "The type of infraction to issue when the filter triggers, or 'NONE'. "
            "If two infractions are triggered for the same message, "
            "the harsher one will be applied (by type or duration). "
            "Superstars will be triggered even if there is a harsher infraction.\n\n"
            "Valid infraction types in order of harshness: "
        ) + ", ".join(infraction.name for infraction in Infraction),
        "infraction_duration": "How long the infraction should last for in seconds, or 'None' for permanent.",
        "infraction_reason": "The reason delivered with the infraction.",
        "dm_content": "The contents of a message to be DMed to the offending user.",
        "dm_embed": "The contents of the embed to be DMed to the offending user."
    }

    dm_content: str | None
    dm_embed: str | None
    infraction_type: Infraction | None
    infraction_reason: str | None
    infraction_duration: float | None

    @validator("infraction_type", pre=True)
    @classmethod
    def convert_infraction_name(cls, infr_type: str) -> Infraction:
        """Convert the string to an Infraction by name."""
        return Infraction[infr_type.replace(" ", "_").upper()] if infr_type else None

    async def action(self, ctx: FilterContext) -> None:
        """Send the notification to the user, and apply any specified infractions."""
        # If there is no infraction to apply, any DM contents already provided in the context take precedence.
        if self.infraction_type is None and (ctx.dm_content or ctx.dm_embed):
            dm_content = ctx.dm_content
            dm_embed = ctx.dm_embed
        else:
            dm_content = self.dm_content
            dm_embed = self.dm_embed

        if dm_content or dm_embed:
            formatting = {"domain": ctx.notification_domain}
            dm_content = f"Hey {ctx.author.mention}!\n{dm_content.format(**formatting)}"
            if dm_embed:
                dm_embed = Embed(description=dm_embed.format(**formatting), colour=Colour.og_blurple())
            else:
                dm_embed = None

            try:
                await ctx.author.send(dm_content, embed=dm_embed)
                ctx.action_descriptions.append("notified")
            except Forbidden:
                ctx.action_descriptions.append("notified (failed)")

        msg_ctx = await bot.instance.get_context(ctx.message)
        msg_ctx.guild = bot.instance.get_guild(Guild.id)
        msg_ctx.author = ctx.author
        msg_ctx.channel = ctx.channel

        if self.infraction_type is not None:
            if self.infraction_type == Infraction.BAN or not hasattr(ctx.channel, "guild"):
                msg_ctx.channel = bot.instance.get_channel(Channels.mod_alerts)
            msg_ctx.command = bot.instance.get_command(self.infraction_type.name.lower())
            await msg_ctx.invoke(
                msg_ctx.command,
                ctx.author,
                arrow.utcnow() + timedelta(seconds=self.infraction_duration)
                if self.infraction_duration is not None else None,
                reason=self.infraction_reason
            )
            ctx.action_descriptions.append(self.infraction_type.name.lower())

    def __or__(self, other: ActionEntry):
        """
        Combines two actions of the same type. Each type of action is executed once per filter.

        If the infractions are different, take the data of the one higher up the hierarchy.

        There is no clear way to properly combine several notification messages, especially when it's in two parts.
        To avoid bombarding the user with several notifications, the message with the more significant infraction
        is used.
        """
        if not isinstance(other, InfractionAndNotification):
            return NotImplemented

        # Lower number -> higher in the hierarchy
        if self.infraction_type is None:
            return other.copy()
        elif other.infraction_type is None:
            return self.copy()
        elif self.infraction_type.value < other.infraction_type.value:
            return self.copy()
        elif self.infraction_type.value > other.infraction_type.value:
            return other.copy()
        else:
            if self.infraction_duration is None or (
                other.infraction_duration is not None and self.infraction_duration > other.infraction_duration
            ):
                result = self.copy()
            else:
                result = other.copy()
            return result
