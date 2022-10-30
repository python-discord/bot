from dataclasses import dataclass
from datetime import timedelta
from enum import Enum, auto
from typing import ClassVar

import arrow
import discord.abc
from botcore.utils.logging import get_logger
from discord import Colour, Embed, Member, User
from discord.errors import Forbidden
from pydantic import validator

import bot as bot_module
from bot.constants import Channels, Guild
from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings_types.settings_entry import ActionEntry

log = get_logger(__name__)


@dataclass
class FakeContext:
    """
    A class representing a context-like object that can be sent to infraction commands.

    The goal is to be able to apply infractions without depending on the existence of a message or an interaction
    (which are the two ways to create a Context), e.g. in API events which aren't message-driven, or in custom filtering
    events.
    """

    channel: discord.abc.Messageable
    bot: bot_module.bot.Bot | None = None
    guild: discord.Guild | None = None
    author: discord.Member | discord.User | None = None
    me: discord.Member | None = None

    def __post_init__(self):
        """Initialize the missing information."""
        if not self.bot:
            self.bot = bot_module.instance
        if not self.guild:
            self.guild = self.bot.get_guild(Guild.id)
        if not self.me:
            self.me = self.guild.me
        if not self.author:
            self.author = self.me

    async def send(self, *args, **kwargs) -> discord.Message:
        """A wrapper for channel.send."""
        return await self.channel.send(*args, **kwargs)


class Infraction(Enum):
    """An enumeration of infraction types. The lower the value, the higher it is on the hierarchy."""

    BAN = auto()
    KICK = auto()
    MUTE = auto()
    VOICE_MUTE = auto()
    SUPERSTAR = auto()
    WARNING = auto()
    WATCH = auto()
    NOTE = auto()

    def __str__(self) -> str:
        return self.name

    async def invoke(
        self,
        user: Member | User,
        channel: discord.abc.Messageable,
        alerts_channel: discord.TextChannel,
        duration: float | None,
        reason: str | None
    ) -> None:
        """Invokes the command matching the infraction name."""
        command_name = self.name.lower()
        command = bot_module.instance.get_command(command_name)
        if not command:
            await alerts_channel.send(f":warning: Could not apply {command_name} to {user.mention}: command not found.")

        ctx = FakeContext(channel)
        if self.name in ("KICK", "WARNING", "WATCH", "NOTE"):
            await command(ctx, user, reason=reason)
        else:
            duration = arrow.utcnow() + timedelta(seconds=duration) if duration else None
            await command(ctx, user, duration, reason=reason)


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
            "the harsher one will be applied (by type or duration).\n\n"
            "Valid infraction types in order of harshness: "
        ) + ", ".join(infraction.name for infraction in Infraction),
        "infraction_duration": "How long the infraction should last for in seconds, or 'None' for permanent.",
        "infraction_reason": "The reason delivered with the infraction.",
        "infraction_channel": (
            "The channel ID in which to invoke the infraction (and send the confirmation message). "
            "If blank, the infraction will be sent in the context channel. If the ID fails to resolve, it will default "
            "to the mod-alerts channel."
        ),
        "dm_content": "The contents of a message to be DMed to the offending user.",
        "dm_embed": "The contents of the embed to be DMed to the offending user."
    }

    dm_content: str | None
    dm_embed: str | None
    infraction_type: Infraction | None
    infraction_reason: str | None
    infraction_duration: float | None
    infraction_channel: int | None

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
                ctx.action_descriptions.append("failed to notify")

        if self.infraction_type is not None:
            alerts_channel = bot_module.instance.get_channel(Channels.mod_alerts)
            if self.infraction_channel:
                channel = bot_module.instance.get_channel(self.infraction_channel)
                if not channel:
                    log.info(f"Could not find a channel with ID {self.infraction_channel}, infracting in mod-alerts.")
                    channel = alerts_channel
            else:
                channel = ctx.channel
            await self.infraction_type.invoke(
                ctx.author, channel, alerts_channel, self.infraction_duration, self.infraction_reason
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
