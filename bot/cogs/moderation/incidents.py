import logging
import typing as t
from enum import Enum

import discord
from discord.ext.commands import Cog

from bot.bot import Bot
from bot.constants import Emojis, Roles

log = logging.getLogger(__name__)


class Signal(Enum):
    """Recognized incident status signals."""

    ACTIONED = Emojis.incident_actioned
    NOT_ACTIONED = Emojis.incident_unactioned
    INVESTIGATING = Emojis.incident_investigating


ALLOWED_ROLES: t.Set[int] = {Roles.moderators, Roles.admins, Roles.owners}
ALLOWED_EMOJI: t.Set[str] = {signal.value for signal in Signal}


class Incidents(Cog):
    """Automation for the #incidents channel."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @staticmethod
    async def add_signals(incident: discord.Message) -> None:
        """Add `Signal` member emoji to `incident` as reactions."""
        for signal_emoji in Signal:
            log.debug(f"Adding reaction: {signal_emoji.value}")
            await incident.add_reaction(signal_emoji.value)

    @Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Pass each incident sent in #incidents to `add_signals`."""
        ...
