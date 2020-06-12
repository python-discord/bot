import asyncio
import logging
import typing as t
from enum import Enum

import discord
from discord.ext.commands import Cog

from bot.bot import Bot
from bot.constants import Channels, Emojis, Roles, Webhooks

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


def own_reactions(message: discord.Message) -> t.Set[str]:
    """Get the set of reactions placed on `message` by the bot itself."""
    return {str(reaction.emoji) for reaction in message.reactions if reaction.me}


def has_signals(message: discord.Message) -> bool:
    """True if `message` already has all `Signal` reactions, False otherwise."""
    missing_signals = ALLOWED_EMOJI - own_reactions(message)
    return not missing_signals


async def add_signals(incident: discord.Message) -> None:
    """Add `Signal` member emoji to `incident` as reactions."""
    existing_reacts = own_reactions(incident)

    for signal_emoji in Signal:

        # This will not raise, but it is a superfluous API call that can be avoided
        if signal_emoji.value in existing_reacts:
            log.debug(f"Skipping emoji as it's already been placed: {signal_emoji}")

        else:
            log.debug(f"Adding reaction: {signal_emoji}")
            await incident.add_reaction(signal_emoji.value)


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
        After adding reactions, we take a short break to avoid drowning in ratelimits.

        Once this task is scheduled, listeners that change messages should await it.
        The crawl assumes that the channel history doesn't change as we go over it.
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

            if not is_incident(message):
                log.debug("Skipping message: not an incident")
                continue

            if has_signals(message):
                log.debug("Skipping message: already has all signals")
                continue

            await add_signals(message)
            await asyncio.sleep(sleep)

        log.debug("Crawl task finished!")

    async def archive(self, incident: discord.Message, outcome: Signal) -> bool:
        """
        Relay `incident` to the #incidents-archive channel.

        The following pieces of information are relayed:
            * Incident message content (clean, pingless)
            * Incident author name (as webhook author)
            * Incident author avatar (as webhook avatar)
            * Resolution signal (`outcome`)

        Return True if the relay finishes successfully. If anything goes wrong, meaning
        not all information was relayed, return False. This signals that the original
        message is not safe to be deleted, as we will lose some information.
        """
        log.debug(f"Archiving incident: {incident.id} with outcome: {outcome}")
        try:
            # First we try to grab the webhook
            webhook: discord.Webhook = await self.bot.fetch_webhook(Webhooks.incidents_archive)

            # Now relay the incident
            message: discord.Message = await webhook.send(
                content=incident.clean_content,  # Clean content will prevent mentions from pinging
                username=incident.author.name,
                avatar_url=incident.author.avatar_url,
                wait=True,  # This makes the method return the sent Message object
            )

            # Finally add the `outcome` emoji
            await message.add_reaction(outcome.value)

        except Exception as exc:
            log.exception("Failed to archive incident to #incidents-archive", exc_info=exc)
            return False

        else:
            log.debug("Message archived successfully!")
            return True

    def make_confirmation_task(self, incident: discord.Message, timeout: int = 5) -> asyncio.Task:
        """
        Create a task to wait `timeout` seconds for `incident` to be deleted.

        If `timeout` passes, this will raise `asyncio.TimeoutError`, signaling that we haven't
        been able to confirm that the message was deleted.
        """
        log.debug(f"Confirmation task will wait {timeout=} seconds for {incident.id=} to be deleted")
        coroutine = self.bot.wait_for(
            event="raw_message_delete",
            check=lambda payload: payload.message_id == incident.id,
            timeout=timeout,
        )
        return self.bot.loop.create_task(coroutine)

    async def process_event(self, reaction: str, incident: discord.Message, member: discord.Member) -> None:
        """
        Process a valid `reaction_add` event in #incidents.

        First, we check that the reaction is a recognized `Signal` member, and that it was sent by
        a permitted user (at least one role in `ALLOWED_ROLES`). If not, the reaction is removed.

        If the reaction was either `Signal.ACTIONED` or `Signal.NOT_ACTIONED`, we attempt to relay
        the report to #incidents-archive. If successful, the original message is deleted.

        We do not release `event_lock` until we receive the corresponding `message_delete` event.
        This ensures that if there is a racing event awaiting the lock, it will fail to find the
        message, and will abort.
        """
        members_roles: t.Set[int] = {role.id for role in member.roles}
        if not members_roles & ALLOWED_ROLES:  # Intersection is truthy on at least 1 common element
            log.debug(f"Removing invalid reaction: user {member} is not permitted to send signals")
            await incident.remove_reaction(reaction, member)
            return

        if reaction not in ALLOWED_EMOJI:
            log.debug(f"Removing invalid reaction: emoji {reaction} is not a valid signal")
            await incident.remove_reaction(reaction, member)
            return

        # If we reach this point, we know that `emoji` is a `Signal` member
        signal = Signal(reaction)
        log.debug(f"Received signal: {signal}")

        if signal not in (Signal.ACTIONED, Signal.NOT_ACTIONED):
            log.debug("Reaction was valid, but no action is currently defined for it")
            return

        relay_successful = await self.archive(incident, signal)
        if not relay_successful:
            log.debug("Original message will not be deleted as we failed to relay it to the archive")
            return

        timeout = 5  # Seconds
        confirmation_task = self.make_confirmation_task(incident, timeout)

        log.debug("Deleting original message")
        await incident.delete()

        log.debug(f"Awaiting deletion confirmation: {timeout=} seconds")
        try:
            await confirmation_task
        except asyncio.TimeoutError:
            log.warning(f"Did not receive incident deletion confirmation within {timeout} seconds!")
        else:
            log.debug("Deletion was confirmed")

    async def resolve_message(self, message_id: int) -> t.Optional[discord.Message]:
        """
        Get `discord.Message` for `message_id` from cache, or API.

        We first look into the local cache to see if the message is present.

        If not, we try to fetch the message from the API. This is necessary for messages
        which were sent before the bot's current session.

        However, in an edge-case, it is also possible that the message was already deleted,
        and the API will return a 404. In such a case, None will be returned. This signals
        that the event for `message_id` should be ignored.
        """
        await self.bot.wait_until_guild_available()  # First make sure that the cache is ready
        log.debug(f"Resolving message for: {message_id=}")
        message: discord.Message = self.bot._connection._get_message(message_id)  # noqa: Private attribute

        if message is not None:
            log.debug("Message was found in cache")
            return message

        log.debug("Message not found, attempting to fetch")
        try:
            message = await self.bot.get_channel(Channels.incidents).fetch_message(message_id)
        except Exception as exc:
            log.debug(f"Failed to fetch message: {exc}")
            return None
        else:
            log.debug("Message fetched successfully!")
            return message

    @Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """
        Pre-process `payload` and pass it to `process_event` if appropriate.

        We abort instantly if `payload` doesn't relate to a message sent in #incidents,
        or if it was sent by a bot.

        If `payload` relates to a message in #incidents, we first ensure that `crawl_task` has
        finished, to make sure we don't mutate channel state as we're crawling it.

        Next, we acquire `event_lock` - to prevent racing, events are processed one at a time.

        Once we have the lock, the `discord.Message` object for this event must be resolved.
        If the lock was previously held by an event which successfully relayed the incident,
        this will fail and we abort the current event.

        Finally, with both the lock and the `discord.Message` instance in our hands, we delegate
        to `process_event` to handle the event.

        The justification for using a raw listener is the need to receive events for messages
        which were not cached in the current session. As a result, a certain amount of
        complexity is introduced, but at the moment this doesn't appear to be avoidable.
        """
        if payload.channel_id != Channels.incidents or payload.member.bot:
            return

        log.debug(f"Received reaction add event in #incidents, waiting for crawler: {self.crawl_task.done()=}")
        await self.crawl_task

        log.debug(f"Acquiring event lock: {self.event_lock.locked()=}")
        async with self.event_lock:
            message = await self.resolve_message(payload.message_id)

            if message is None:
                log.debug("Listener will abort as related message does not exist!")
                return

            if not is_incident(message):
                log.debug("Ignoring event for a non-incident message")
                return

            await self.process_event(str(payload.emoji), message, payload.member)
            log.debug("Releasing event lock")

    @Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Pass `message` to `add_signals` if and only if it satisfies `is_incident`."""
        if is_incident(message):
            await add_signals(message)
