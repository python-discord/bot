from enum import Enum, auto
from typing import ClassVar, Self

import arrow
import discord.abc
from dateutil.relativedelta import relativedelta
from discord import Colour, Embed, Member, User
from discord.errors import Forbidden
from pydantic import field_validator
from pydis_core.utils.logging import get_logger
from pydis_core.utils.members import get_or_fetch_member

import bot as bot_module
from bot.constants import Channels
from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings_types.settings_entry import ActionEntry
from bot.exts.filtering._utils import CustomIOField, FakeContext
from bot.utils.time import humanize_delta, parse_duration_string, relativedelta_to_timedelta

log = get_logger(__name__)

passive_form = {
    "BAN": "banned",
    "KICK": "kicked",
    "TIMEOUT": "timed out",
    "VOICE_MUTE": "voice muted",
    "SUPERSTAR": "superstarred",
    "WARNING": "warned",
    "WATCH": "watch",
    "NOTE": "noted",
}


class InfractionDuration(CustomIOField):
    """A field that converts a string to a duration and presents it in a human-readable format."""

    @classmethod
    def process_value(cls, v: str | relativedelta) -> relativedelta:
        """
        Transform the given string into a relativedelta.

        Raise a ValueError if the conversion is not possible.
        """
        if isinstance(v, relativedelta):
            return v

        try:
            v = float(v)
        except ValueError:  # Not a float.
            if not (delta := parse_duration_string(v)):
                raise ValueError(f"`{v}` is not a valid duration string.")
        else:
            delta = relativedelta(seconds=float(v)).normalized()

        return delta

    def serialize(self) -> float:
        """The serialized value is the total number of seconds this duration represents."""
        return relativedelta_to_timedelta(self.value).total_seconds()

    def __str__(self):
        """Represent the stored duration in a human-readable format."""
        return humanize_delta(self.value, max_units=2) if self.value else "Permanent"


class Infraction(Enum):
    """An enumeration of infraction types. The lower the value, the higher it is on the hierarchy."""

    BAN = auto()
    KICK = auto()
    TIMEOUT = auto()
    VOICE_MUTE = auto()
    SUPERSTAR = auto()
    WARNING = auto()
    WATCH = auto()
    NOTE = auto()
    NONE = auto()

    def __str__(self) -> str:
        return self.name

    async def invoke(
        self,
        user: Member | User,
        message: discord.Message,
        channel: discord.abc.GuildChannel | discord.DMChannel,
        alerts_channel: discord.TextChannel,
        duration: InfractionDuration,
        reason: str
    ) -> None:
        """Invokes the command matching the infraction name."""
        command_name = self.name.lower()
        command = bot_module.instance.get_command(command_name)
        if not command:
            await alerts_channel.send(f":warning: Could not apply {command_name} to {user.mention}: command not found.")
            log.warning(f":warning: Could not apply {command_name} to {user.mention}: command not found.")
            return

        if isinstance(user, discord.User):  # For example because a message was sent in a DM.
            member = await get_or_fetch_member(channel.guild, user.id)
            if member:
                user = member
            else:
                log.warning(
                    f"The user {user} were set to receive an automatic {command_name}, "
                    "but they were not found in the guild."
                )
                return

        ctx = FakeContext(message, channel, command)
        if self.name in ("KICK", "WARNING", "WATCH", "NOTE"):
            await command(ctx, user, reason=reason or None)
        else:
            duration = arrow.utcnow().datetime + duration.value if duration.value else None
            await command(ctx, user, duration, reason=reason or None)


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
        "infraction_duration": (
            "How long the infraction should last for in seconds. 0 for permanent. "
            "Also supports durations as in an infraction invocation (such as `10d`)."
        ),
        "infraction_reason": "The reason delivered with the infraction.",
        "infraction_channel": (
            "The channel ID in which to invoke the infraction (and send the confirmation message). "
            "If 0, the infraction will be sent in the context channel. If the ID otherwise fails to resolve, "
            "it will default to the mod-alerts channel."
        ),
        "dm_content": "The contents of a message to be DMed to the offending user. Doesn't send when invoked in DMs.",
        "dm_embed": "The contents of the embed to be DMed to the offending user. Doesn't send when invoked in DMs."
    }

    dm_content: str
    dm_embed: str
    infraction_type: Infraction
    infraction_reason: str
    infraction_duration: InfractionDuration
    infraction_channel: int

    @field_validator("infraction_type", mode="before")
    @classmethod
    def convert_infraction_name(cls, infr_type: str | Infraction) -> Infraction:
        """Convert the string to an Infraction by name."""
        if isinstance(infr_type, Infraction):
            return infr_type
        return Infraction[infr_type.replace(" ", "_").upper()]

    async def send_message(self, ctx: FilterContext) -> None:
        """Send the notification to the user."""
        # If there is no infraction to apply, any DM contents already provided in the context take precedence.
        if self.infraction_type == Infraction.NONE and (ctx.dm_content or ctx.dm_embed):
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

    async def action(self, ctx: FilterContext) -> None:
        """Send the notification to the user, and apply any specified infractions."""
        if ctx.in_guild:  # Don't DM the user for filters invoked in DMs.
            await self.send_message(ctx)

        if self.infraction_type != Infraction.NONE:
            alerts_channel = bot_module.instance.get_channel(Channels.mod_alerts)
            if self.infraction_channel:
                channel = bot_module.instance.get_channel(self.infraction_channel)
                if not channel:
                    log.info(f"Could not find a channel with ID {self.infraction_channel}, infracting in mod-alerts.")
                    channel = alerts_channel
            elif not ctx.channel:
                channel = alerts_channel
            else:
                channel = ctx.channel
            if not channel:  # If somehow it's set to `alerts_channel` and it can't be found.
                log.error(f"Unable to apply infraction as the context channel {channel} can't be found.")
                return

            await self.infraction_type.invoke(
                ctx.author, ctx.message, channel, alerts_channel, self.infraction_duration, self.infraction_reason
            )
            ctx.action_descriptions.append(passive_form[self.infraction_type.name])

    def union(self, other: Self) -> Self:
        """
        Combines two actions of the same type. Each type of action is executed once per filter.

        If the infractions are different, take the data of the one higher up the hierarchy.

        There is no clear way to properly combine several notification messages, especially when it's in two parts.
        To avoid bombarding the user with several notifications, the message with the more significant infraction
        is used. If the more significant infraction has no accompanying message, use the one from the other infraction,
        if it exists.
        """
        # Lower number -> higher in the hierarchy
        if self.infraction_type is None:
            return other.model_copy()
        if other.infraction_type is None:
            return self.model_copy()

        if self.infraction_type.value < other.infraction_type.value:
            result = self.model_copy()
        elif self.infraction_type.value > other.infraction_type.value:
            result = other.model_copy()
            other = self
        else:
            now = arrow.utcnow().datetime
            if self.infraction_duration is None or (
                other.infraction_duration is not None
                and now + self.infraction_duration.value > now + other.infraction_duration.value
            ):
                result = self.model_copy()
            else:
                result = other.model_copy()
                other = self

        # If the winner has no message but the loser does, copy the message to the winner.
        result_overrides = result.overrides
        # Either take both or nothing, don't mix content from one filter and embed from another.
        if "dm_content" not in result_overrides and "dm_embed" not in result_overrides:
            other_overrides = other.overrides
            if "dm_content" in other_overrides:
                result.dm_content = other_overrides["dm_content"]
            if "dm_embed" in other_overrides:
                result.dm_content = other_overrides["dm_embed"]

        return result
