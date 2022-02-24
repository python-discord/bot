from collections import namedtuple
from datetime import timedelta
from enum import Enum, auto
from typing import Any, Optional

import arrow
from discord import Colour, Embed
from discord.errors import Forbidden

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
    NONE = auto()  # Allows making operations on an entry with no infraction without checking for None.

    def __bool__(self) -> bool:
        """
        Make the NONE value false-y.

        This is useful for Settings.create to evaluate whether the entry contains anything.
        """
        return self != Infraction.NONE


superstar = namedtuple("superstar", ["reason", "duration"])


class InfractionAndNotification(ActionEntry):
    """
    A setting entry which specifies what infraction to issue and the notification to DM the user.

    Since a DM cannot be sent when a user is banned or kicked, these two functions need to be grouped together.
    """

    name = "infraction_and_notification"

    def __init__(self, entry_data: Any):
        super().__init__(entry_data)

        if entry_data["infraction_type"]:
            self.infraction_type = entry_data["infraction_type"]
            if isinstance(self.infraction_type, str):
                self.infraction_type = Infraction[self.infraction_type.replace(" ", "_").upper()]
            self.infraction_reason = entry_data["infraction_reason"]
            if entry_data["infraction_duration"] is not None:
                self.infraction_duration = float(entry_data["infraction_duration"])
            else:
                self.infraction_duration = None
        else:
            self.infraction_type = Infraction.NONE
            self.infraction_reason = None
            self.infraction_duration = 0

        self.dm_content = entry_data["dm_content"]
        self.dm_embed = entry_data["dm_embed"]

        self._superstar = entry_data.get("superstar", None)

    async def action(self, ctx: FilterContext) -> None:
        """Send the notification to the user, and apply any specified infractions."""
        # If there is no infraction to apply, any DM contents already provided in the context take precedence.
        if self.infraction_type == Infraction.NONE and (ctx.dm_content or ctx.dm_embed):
            dm_content = ctx.dm_content
            dm_embed = ctx.dm_embed
        else:
            dm_content = self.dm_content
            dm_embed = self.dm_embed

        if dm_content or dm_embed:
            dm_content = f"Hey {ctx.author.mention}!\n{dm_content}"
            dm_embed = Embed(description=dm_embed, colour=Colour.og_blurple())

            try:
                await ctx.author.send(dm_content, embed=dm_embed)
                ctx.action_descriptions.append("notified")
            except Forbidden:
                ctx.action_descriptions.append("notified (failed)")

        msg_ctx = await bot.instance.get_context(ctx.message)
        msg_ctx.guild = bot.instance.get_guild(Guild.id)
        msg_ctx.author = ctx.author
        msg_ctx.channel = ctx.channel
        if self._superstar:
            msg_ctx.command = bot.instance.get_command("superstarify")
            await msg_ctx.invoke(
                msg_ctx.command,
                ctx.author,
                arrow.utcnow() + timedelta(seconds=self._superstar.duration)
                if self._superstar.duration is not None else None,
                reason=self._superstar.reason
            )
            ctx.action_descriptions.append("superstar")

        if self.infraction_type != Infraction.NONE:
            if self.infraction_type == Infraction.BAN or not hasattr(ctx.channel, "guild"):
                msg_ctx.channel = bot.instance.get_channel(Channels.mod_alerts)
            msg_ctx.command = bot.instance.get_command(self.infraction_type.name)
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

        A special case is made for superstar infractions. Even if we decide to auto-mute a user, if they have a
        particularly problematic username we will still want to superstarify them.

        This is a "best attempt" implementation. Trying to account for any type of combination would create an
        extremely complex ruleset. For example, we could special-case watches as well.

        There is no clear way to properly combine several notification messages, especially when it's in two parts.
        To avoid bombarding the user with several notifications, the message with the more significant infraction
        is used.
        """
        if not isinstance(other, InfractionAndNotification):
            return NotImplemented

        # Lower number -> higher in the hierarchy
        if self.infraction_type.value < other.infraction_type.value and other.infraction_type != Infraction.SUPERSTAR:
            result = InfractionAndNotification(self.to_dict())
            result._superstar = self._merge_superstars(self._superstar, other._superstar)
            return result
        elif self.infraction_type.value > other.infraction_type.value and self.infraction_type != Infraction.SUPERSTAR:
            result = InfractionAndNotification(other.to_dict())
            result._superstar = self._merge_superstars(self._superstar, other._superstar)
            return result

        if self.infraction_type == other.infraction_type:
            if self.infraction_duration is None or (
                    other.infraction_duration is not None and self.infraction_duration > other.infraction_duration
            ):
                result = InfractionAndNotification(self.to_dict())
            else:
                result = InfractionAndNotification(other.to_dict())
            result._superstar = self._merge_superstars(self._superstar, other._superstar)
            return result

        # At this stage the infraction types are different, and the lower one is a superstar.
        if self.infraction_type.value < other.infraction_type.value:
            result = InfractionAndNotification(self.to_dict())
            result._superstar = superstar(other.infraction_reason, other.infraction_duration)
        else:
            result = InfractionAndNotification(other.to_dict())
            result._superstar = superstar(self.infraction_reason, self.infraction_duration)
        return result

    @staticmethod
    def _merge_superstars(superstar1: Optional[superstar], superstar2: Optional[superstar]) -> Optional[superstar]:
        """Take the superstar with the greater duration."""
        if not superstar1:
            return superstar2
        if not superstar2:
            return superstar1

        if superstar1.duration is None or superstar1.duration > superstar2.duration:
            return superstar1
        return superstar2
