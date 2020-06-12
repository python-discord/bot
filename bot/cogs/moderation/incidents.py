import asyncio
import logging
import typing as t
from enum import Enum

import discord
from discord.ext.commands import Cog

from bot.bot import Bot
from bot.constants import Channels, Emojis, Roles

log = logging.getLogger(__name__)


class Signal(Enum):
    """Recognized incident status signals."""

    ACTIONED = Emojis.incident_actioned
    NOT_ACTIONED = Emojis.incident_unactioned
    INVESTIGATING = Emojis.incident_investigating


ALLOWED_ROLES: t.Set[int] = {Roles.moderators, Roles.admins, Roles.owners}
ALLOWED_EMOJI: t.Set[str] = {signal.value for signal in Signal}


def is_incident(message: discord.Message) -> bool:
    """True if `message` qualifies as an incident, False otherwise."""
    conditions = (
        message.channel.id == Channels.incidents,  # Message sent in #incidents
        not message.author.bot,                    # Not by a bot
        not message.content.startswith("#"),       # Doesn't start with a hash
        not message.pinned,                        # And isn't header
    )
    return all(conditions)


class Incidents(Cog):
    """Automation for the #incidents channel."""

    def __init__(self, bot: Bot) -> None:
        """Prepare `event_lock` and schedule `crawl_task` on start-up."""
        self.bot = bot

        self.event_lock = asyncio.Lock()
        self.crawl_task = self.bot.loop.create_task(self.crawl_incidents())

    async def crawl_incidents(self) -> None:
        """
        Crawl #incidents and add missing emoji where necessary.

        This is to catch-up should an incident be reported while the bot wasn't listening.
        Internally, we simply walk the channel history and pass each message to `on_message`.

        In order to avoid drowning in ratelimits, we take breaks after each message.

        Once this task is scheduled, listeners should await it. The crawl assumes that
        the channel history doesn't change as we go over it.
        """
        await self.bot.wait_until_guild_available()
        incidents: discord.TextChannel = self.bot.get_channel(Channels.incidents)

        # Limit the query at 50 as in practice, there should never be this many messages,
        # and if there are, something has likely gone very wrong
        limit = 50

        # Seconds to sleep after each message
        sleep = 2

        log.debug(f"Crawling messages in #incidents: {limit=}, {sleep=}")
        async for message in incidents.history(limit=limit):
            await self.on_message(message)
            await asyncio.sleep(sleep)

        log.debug("Crawl task finished!")

    @staticmethod
    async def add_signals(incident: discord.Message) -> None:
        """Add `Signal` member emoji to `incident` as reactions."""
        existing_reacts = {str(reaction.emoji) for reaction in incident.reactions if reaction.me}

        for signal_emoji in Signal:

            # This will not raise, but it is a superfluous API call that can be avoided
            if signal_emoji.value in existing_reacts:
                log.debug(f"Skipping emoji as it's already been placed: {signal_emoji}")

            else:
                log.debug(f"Adding reaction: {signal_emoji}")
                await incident.add_reaction(signal_emoji.value)

    @Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Pass `message` to `add_signals` if and only if it satisfies `is_incident`."""
        if is_incident(message):
            await self.add_signals(message)
