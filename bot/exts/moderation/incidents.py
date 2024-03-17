import asyncio
import re
from datetime import UTC, datetime
from enum import Enum

import discord
from async_rediscache import RedisCache
from discord.ext.commands import Cog, Context, MessageConverter, MessageNotFound
from pydis_core.utils import scheduling

from bot.bot import Bot
from bot.constants import Channels, Colours, Emojis, Guild, Roles, Webhooks
from bot.log import get_logger
from bot.utils.messages import format_user, sub_clyde
from bot.utils.time import TimestampFormats, discord_timestamp

log = get_logger(__name__)

# Amount of messages for `crawl_task` to process at most on start-up - limited to 50
# as in practice, there should never be this many messages, and if there are,
# something has likely gone very wrong
CRAWL_LIMIT = 50

# Seconds for `crawl_task` to sleep after adding reactions to a message
CRAWL_SLEEP = 2

DISCORD_MESSAGE_LINK_RE = re.compile(
    r"(https?://(?:(ptb|canary|www)\.)?discord(?:app)?\.com/channels/"
    r"[0-9]{15,20}"
    r"/[0-9]{15,20}/[0-9]{15,20})"
)


class Signal(Enum):
    """
    Recognized incident status signals.

    This binds emoji to actions. The bot will only react to emoji linked here.
    All other signals are seen as invalid.
    """

    ACTIONED = Emojis.incident_actioned
    NOT_ACTIONED = Emojis.incident_unactioned
    INVESTIGATING = Emojis.incident_investigating


# Reactions from non-mod roles will be removed
ALLOWED_ROLES: set[int] = set(Guild.moderation_roles)

# Message must have all of these emoji to pass the `has_signals` check
ALL_SIGNALS: set[str] = {signal.value for signal in Signal}

# An embed coupled with an optional file to be dispatched
# If the file is not None, the embed attempts to show it in its body
FileEmbed = tuple[discord.Embed, discord.File | None]


async def download_file(attachment: discord.Attachment) -> discord.File | None:
    """
    Download & return `attachment` file.

    If the download fails, the reason is logged and None will be returned.
    404 and 403 errors are only logged at debug level.
    """
    log.debug(f"Attempting to download attachment: {attachment.filename}")
    try:
        return await attachment.to_file()
    except (discord.NotFound, discord.Forbidden) as exc:
        log.debug(f"Failed to download attachment: {exc}")
    except Exception:
        log.exception("Failed to download attachment")


async def make_embed(incident: discord.Message, outcome: Signal, actioned_by: discord.Member) -> FileEmbed:
    """
    Create an embed representation of `incident` for the #incidents-archive channel.

    The name & discriminator of `actioned_by` and `outcome` will be presented in the
    embed footer. Additionally, the embed is coloured based on `outcome`.

    The author of `incident` is not shown in the embed. It is assumed that this piece
    of information will be relayed in other ways, e.g. webhook username.

    As mentions in embeds do not ping, we do not need to use `incident.clean_content`.

    If `incident` contains attachments, the first attachment will be downloaded and
    returned alongside the embed. The embed attempts to display the attachment.
    Should the download fail, we fallback on linking the `proxy_url`, which should
    remain functional for some time after the original message is deleted.
    """
    log.trace(f"Creating embed for {incident.id=}")

    if outcome is Signal.ACTIONED:
        colour = Colours.soft_green
        footer = f"Actioned by {actioned_by}"
    else:
        colour = Colours.soft_red
        footer = f"Rejected by {actioned_by}"

    reported_timestamp = discord_timestamp(incident.created_at)
    relative_timestamp = discord_timestamp(incident.created_at, TimestampFormats.RELATIVE)
    reported_on_msg = f"*Reported {reported_timestamp} ({relative_timestamp}).*"

    # If the description will be too long (>4096 total characters), truncate the incident content
    if len(incident.content) > (allowed_content_chars := 4096-len(reported_on_msg)-2):  # -2 for the newlines
        description = incident.content[:allowed_content_chars-3] + f"...\n\n{reported_on_msg}"
    else:
        description = incident.content + f"\n\n{reported_on_msg}"

    embed = discord.Embed(
        description=description,
        colour=colour,
        timestamp=datetime.now(UTC)
    )
    embed.set_footer(text=footer, icon_url=actioned_by.display_avatar.url)

    if incident.attachments:
        attachment = incident.attachments[0]  # User-sent messages can only contain one attachment
        file = await download_file(attachment)

        if file is not None:
            embed.set_image(url=f"attachment://{attachment.filename}")  # Embed displays the attached file
        else:
            embed.set_author(name="[Failed to relay attachment]", url=attachment.proxy_url)  # Embed links the file
    else:
        file = discord.utils.MISSING

    return embed, file


def is_incident(message: discord.Message) -> bool:
    """True if `message` qualifies as an incident, False otherwise."""
    conditions = (
        message.channel.id == Channels.incidents,  # Message sent in #incidents
        not message.author.bot,                    # Not by a bot
        not message.content.startswith("#"),       # Doesn't start with a hash
        not message.pinned,                        # Isn't header
        not message.reference,                     # And is not a reply
    )
    return all(conditions)


def own_reactions(message: discord.Message) -> set[str]:
    """Get the set of reactions placed on `message` by the bot itself."""
    return {str(reaction.emoji) for reaction in message.reactions if reaction.me}


def has_signals(message: discord.Message) -> bool:
    """True if `message` already has all `Signal` reactions, False otherwise."""
    return ALL_SIGNALS.issubset(own_reactions(message))


def shorten_text(text: str) -> str:
    """
    Truncate the text if there are over 3 lines or 300 characters, or if it is a single word.

    The maximum length of the string would be 303 characters across 3 lines at maximum.
    """
    original_length = len(text)
    # Truncate text to a maximum of 300 characters
    if len(text) > 300:
        text = text[:300]

    # Limit to a maximum of three lines
    text = "\n".join(text.split("\n", maxsplit=3)[:3])

    # If it is a single word, then truncate it to 50 characters
    if text.find(" ") == -1:
        text = text[:50]

    # Remove extra whitespaces from the `text`
    text = text.strip()

    # Add placeholder if the text was shortened
    if len(text) < original_length:
        text = f"{text}..."

    return text


async def make_message_link_embed(ctx: Context, message_link: str) -> discord.Embed | None:
    """
    Create an embedded representation of the discord message link contained in the incident report.

    The Embed would contain the following information -->
        Author: @Jason Terror ♦ (736234578745884682)
        Channel: Special/#bot-commands (814190307980607493)
        Content: This is a very important message!
    """
    embed = None

    try:
        message: discord.Message = await MessageConverter().convert(ctx, message_link)
    except MessageNotFound:
        mod_logs_channel = ctx.bot.get_channel(Channels.mod_log)

        last_100_logs: list[discord.Message] = [message async for message in mod_logs_channel.history(limit=100)]

        for log_entry in last_100_logs:
            if not log_entry.embeds:
                continue

            log_embed: discord.Embed = log_entry.embeds[0]
            if (
                    log_embed.author.name == "Message deleted"
                    and f"[Jump to message]({message_link})" in log_embed.description
            ):
                embed = discord.Embed(
                    colour=discord.Colour.dark_gold(),
                    title="Deleted Message Link",
                    description=(
                        f"Found <#{Channels.mod_log}> entry for deleted message: "
                        f"[Jump to message]({log_entry.jump_url})."
                    )
                )
        if not embed:
            embed = discord.Embed(
                colour=discord.Colour.red(),
                title="Bad Message Link",
                description=f"Message {message_link} not found."
            )
    except discord.DiscordException as e:
        log.exception(f"Failed to make message link embed for '{message_link}', raised exception: {e}")
    else:
        channel = message.channel
        if not channel.permissions_for(channel.guild.get_role(Roles.helpers)).view_channel:
            log.info(
                f"Helpers don't have read permissions in #{channel.name},"
                f" not sending message link embed for {message_link}"
            )
            return None

        embed = discord.Embed(
            colour=discord.Colour.gold(),
            description=(
                f"**Author:** {format_user(message.author)}\n"
                f"**Channel:** {channel.mention} ({channel.category}"
                f"{f'/#{channel.parent.name} - ' if isinstance(channel, discord.Thread) else '/#'}"
                f"{channel.name})\n"
            ),
            timestamp=message.created_at
        )
        embed.set_author(name=message.author, icon_url=message.author.display_avatar.url)
        embed.add_field(
            name="Content",
            value=shorten_text(message.content) if message.content else "[No Message Content]"
        )
        embed.set_footer(text=f"Message ID: {message.id}")

        if message.attachments:
            embed.set_image(url=message.attachments[0].url)

    return embed


async def add_signals(incident: discord.Message) -> None:
    """
    Add `Signal` member emoji to `incident` as reactions.

    If the emoji has already been placed on `incident` by the bot, it will be skipped.
    """
    existing_reacts = own_reactions(incident)

    for signal_emoji in Signal:
        if signal_emoji.value in existing_reacts:  # This would not raise, but it is a superfluous API call
            log.trace(f"Skipping emoji as it's already been placed: {signal_emoji}")
        else:
            log.trace(f"Adding reaction: {signal_emoji}")
            try:
                await incident.add_reaction(signal_emoji.value)
            except discord.NotFound as e:
                if e.code != 10008:
                    raise

                log.trace(f"Couldn't react with signal because message {incident.id} was deleted; skipping incident")
                return


class Incidents(Cog):
    """
    Automation for the #incidents channel.

    This cog does not provide a command API, it only reacts to the following events.

    On start-up:
        * Crawl #incidents and add missing `Signal` emoji where appropriate
        * This is to retro-actively add the available options for messages which
          were sent while the bot wasn't listening
        * Pinned messages and message starting with # do not qualify as incidents
        * See: `crawl_incidents`

    On message:
        * Run message through `extract_message_links` and send them into the channel
        * Add `Signal` member emoji if message qualifies as an incident
        * Ignore messages starting with #
            * Use this if verbal communication is necessary
            * Each such message must be deleted manually once appropriate
        * See: `on_message`

    On reaction:
        * Remove reaction if not permitted
            * User does not have any of the roles in `ALLOWED_ROLES`
            * Used emoji is not a `Signal` member
        * If `Signal.ACTIONED` or `Signal.NOT_ACTIONED` were chosen, attempt to
          relay the incident message to #incidents-archive
        * If relay successful, delete original message
        * Delete quotation message if cached
        * See: `on_raw_reaction_add`

    Please refer to function docstrings for implementation details.
    """

    # This dictionary maps an incident report message to the message link embed's ID
    # RedisCache[discord.Message.id, discord.Message.id]
    message_link_embeds_cache = RedisCache()

    def __init__(self, bot: Bot) -> None:
        """Prepare `event_lock` and schedule `crawl_task` on start-up."""
        self.bot = bot
        self.incidents_webhook = None

        scheduling.create_task(self.fetch_webhook())

        self.event_lock = asyncio.Lock()
        self.crawl_task = scheduling.create_task(self.crawl_incidents())

    async def fetch_webhook(self) -> None:
        """Fetch the incidents webhook object, so we can post message link embeds to it."""
        await self.bot.wait_until_guild_available()

        try:
            self.incidents_webhook = await self.bot.fetch_webhook(Webhooks.incidents.id)
        except discord.HTTPException:
            log.error(f"Failed to fetch incidents webhook with id `{Webhooks.incidents.id}`.")

    async def crawl_incidents(self) -> None:
        """
        Crawl #incidents and add missing emoji where necessary.

        This is to catch-up should an incident be reported while the bot wasn't listening.
        After adding each reaction, we take a short break to avoid drowning in ratelimits.

        Once this task is scheduled, listeners that change messages should await it.
        The crawl assumes that the channel history doesn't change as we go over it.

        Behaviour is configured by: `CRAWL_LIMIT`, `CRAWL_SLEEP`.
        """
        await self.bot.wait_until_guild_available()
        incidents: discord.TextChannel = self.bot.get_channel(Channels.incidents)

        log.debug(f"Crawling messages in #incidents: {CRAWL_LIMIT=}, {CRAWL_SLEEP=}")
        async for message in incidents.history(limit=CRAWL_LIMIT):

            if not is_incident(message):
                log.trace(f"Skipping message {message.id}: not an incident")
                continue

            if has_signals(message):
                log.trace(f"Skipping message {message.id}: already has all signals")
                continue

            await add_signals(message)
            await asyncio.sleep(CRAWL_SLEEP)

        log.debug("Crawl task finished!")

    async def archive(self, incident: discord.Message, outcome: Signal, actioned_by: discord.Member) -> bool:
        """
        Relay an embed representation of `incident` to the #incidents-archive channel.

        The following pieces of information are relayed:
            * Incident message content (as embed description)
            * Incident attachment (if image, shown in archive embed)
            * Incident author name (as webhook author)
            * Incident author avatar (as webhook avatar)
            * Resolution signal `outcome` (as embed colour & footer)
            * Moderator `actioned_by` (name & discriminator shown in footer)

        If `incident` contains an attachment, we try to add it to the archive embed. There is
        no handing of extensions / file types - we simply dispatch the attachment file with the
        webhook, and try to display it in the embed. Testing indicates that if the attachment
        cannot be displayed (e.g. a text file), it's invisible in the embed, with no error.

        Return True if the relay finishes successfully. If anything goes wrong, meaning
        not all information was relayed, return False. This signals that the original
        message is not safe to be deleted, as we will lose some information.
        """
        log.info(f"Archiving incident: {incident.id} (outcome: {outcome}, actioned by: {actioned_by})")
        embed, attachment_file = await make_embed(incident, outcome, actioned_by)

        try:
            webhook = await self.bot.fetch_webhook(Webhooks.incidents_archive.id)
            await webhook.send(
                embed=embed,
                username=sub_clyde(incident.author.display_name),
                avatar_url=incident.author.display_avatar.url,
                file=attachment_file,
            )
        except Exception:
            log.exception(f"Failed to archive incident {incident.id} to #incidents-archive")
            return False
        else:
            log.trace("Message archived successfully!")
            return True

    def make_confirmation_task(self, incident: discord.Message, timeout: int = 5) -> asyncio.Task:
        """
        Create a task to wait `timeout` seconds for `incident` to be deleted.

        If `timeout` passes, this will raise `asyncio.TimeoutError`, signaling that we haven't
        been able to confirm that the message was deleted.
        """
        log.trace(f"Confirmation task will wait {timeout=} seconds for {incident.id=} to be deleted")

        def check(payload: discord.RawReactionActionEvent) -> bool:
            return payload.message_id == incident.id

        coroutine = self.bot.wait_for("raw_message_delete", check=check, timeout=timeout)
        return scheduling.create_task(coroutine)

    async def process_event(self, reaction: str, incident: discord.Message, member: discord.Member) -> None:
        """
        Process a `reaction_add` event in #incidents.

        First, we check that the reaction is a recognized `Signal` member, and that it was sent by
        a permitted user (at least one role in `ALLOWED_ROLES`). If not, the reaction is removed.

        If the reaction was either `Signal.ACTIONED` or `Signal.NOT_ACTIONED`, we attempt to relay
        the report to #incidents-archive. If successful, the original message is deleted.

        We do not release `event_lock` until we receive the corresponding `message_delete` event.
        This ensures that if there is a racing event awaiting the lock, it will fail to find the
        message, and will abort. There is a `timeout` to ensure that this doesn't hold the lock
        forever should something go wrong.

        Deletes cache value (`message_link_embeds_cache`) of `incident` if it exists. It then removes the
        webhook message for that particular link from the channel.
        """
        members_roles: set[int] = {role.id for role in member.roles}
        if not members_roles & ALLOWED_ROLES:  # Intersection is truthy on at least 1 common element
            log.debug(f"Removing invalid reaction: user {member} is not permitted to send signals")
            try:
                await incident.remove_reaction(reaction, member)
            except discord.NotFound:
                log.trace("Couldn't remove reaction because the reaction or its message was deleted")
            return

        try:
            signal = Signal(reaction)
        except ValueError:
            log.debug(f"Removing invalid reaction: emoji {reaction} is not a valid signal")
            try:
                await incident.remove_reaction(reaction, member)
            except discord.NotFound:
                log.trace("Couldn't remove reaction because the reaction or its message was deleted")
            return

        log.trace(f"Received signal: {signal}")

        if signal not in (Signal.ACTIONED, Signal.NOT_ACTIONED):
            log.debug("Reaction was valid, but no action is currently defined for it")
            return

        relay_successful = await self.archive(incident, signal, actioned_by=member)
        if not relay_successful:
            log.trace("Original message will not be deleted as we failed to relay it to the archive")
            return

        timeout = 5  # Seconds
        confirmation_task = self.make_confirmation_task(incident, timeout)

        log.trace("Deleting original message")
        try:
            await incident.delete()
        except discord.NotFound:
            log.trace("Couldn't delete message because it was already deleted")

        log.trace(f"Awaiting deletion confirmation: {timeout=} seconds")
        try:
            await confirmation_task
        except TimeoutError:
            log.info(f"Did not receive incident deletion confirmation within {timeout} seconds!")
        else:
            log.trace("Deletion was confirmed")

        if self.incidents_webhook:
            # Deletes the message link embeds found in cache from the channel and cache.
            await self.delete_msg_link_embed(incident.id)

    async def resolve_message(self, message_id: int) -> discord.Message | None:
        """
        Get `discord.Message` for `message_id` from cache, or API.

        We first look into the local cache to see if the message is present.

        If not, we try to fetch the message from the API. This is necessary for messages
        which were sent before the bot's current session.

        In an edge-case, it is also possible that the message was already deleted, and
        the API will respond with a 404. In such a case, None will be returned.
        This signals that the event for `message_id` should be ignored.
        """
        await self.bot.wait_until_guild_available()  # First make sure that the cache is ready
        log.trace(f"Resolving message for: {message_id=}")
        message: discord.Message | None = self.bot._connection._get_message(message_id)

        if message is not None:
            log.trace("Message was found in cache")
            return message

        log.trace("Message not found, attempting to fetch")
        try:
            message = await self.bot.get_channel(Channels.incidents).fetch_message(message_id)
        except discord.NotFound:
            log.trace("Message doesn't exist, it was likely already relayed")
        except Exception:
            log.exception(f"Failed to fetch message {message_id}!")
        else:
            log.trace("Message fetched successfully!")
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

        log.trace(f"Received reaction add event in #incidents, waiting for crawler: {self.crawl_task.done()=}")
        await self.crawl_task

        log.trace(f"Acquiring event lock: {self.event_lock.locked()=}")
        async with self.event_lock:
            message = await self.resolve_message(payload.message_id)

            if message is None:
                log.debug("Listener will abort as related message does not exist!")
                return

            if not is_incident(message):
                log.debug("Ignoring event for a non-incident message")
                return

            await self.process_event(str(payload.emoji), message, payload.member)
            log.trace("Releasing event lock")

    @Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """
        Pass `message` to `add_signals` and `extract_message_links` if it satisfies `is_incident`.

        If `message` is an incident report, then run it through `extract_message_links` to get all
        the message link embeds (embeds which contain information about that particular link).
        These message link embeds are then sent into the channel.

        Also passes the message into `add_signals` if the message is an incident.
        """
        if not is_incident(message):
            return

        await add_signals(message)

        # Only use this feature if incidents webhook embed is found
        if self.incidents_webhook:
            if embed_list := await self.extract_message_links(message):
                await self.send_message_link_embeds(embed_list, message, self.incidents_webhook)

    @Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        """
        Delete message link embeds for `payload.message_id`.

        Search through the cache for message, if found delete it from cache and channel.
        """
        if self.incidents_webhook:
            await self.delete_msg_link_embed(payload.message_id)

    async def extract_message_links(self, message: discord.Message) -> list[discord.Embed] | None:
        """
        Check if there's any message links in the text content.

        Then pass the message_link into `make_message_link_embed` to format an
        embed for it containing information about the link.

        As Discord only allows a max of 10 embeds in a single webhook, just send the
        first 10 embeds and don't care about the rest.

        If no links are found for the message, just log a trace statement.
        """
        message_links = DISCORD_MESSAGE_LINK_RE.findall(message.content)
        if not message_links:
            log.trace(
                f"No message links detected on incident message with id {message.id}."
            )
            return None

        embeds = []
        for message_link in message_links[:10]:
            ctx = await self.bot.get_context(message)
            embed = await make_message_link_embed(ctx, message_link[0])
            if embed:
                embeds.append(embed)

        return embeds

    async def send_message_link_embeds(
            self,
            webhook_embed_list: list,
            message: discord.Message,
            webhook: discord.Webhook,
    ) -> int | None:
        """
        Send message link embeds to #incidents channel.

        Using the `webhook` passed in as a parameter to send
        the embeds in the `webhook_embed_list` parameter.

        After sending each embed it maps the `message.id`
        to the `webhook_msg_ids` IDs in the async redis-cache.
        """
        try:
            webhook_msg = await webhook.send(
                embeds=[embed for embed in webhook_embed_list if embed],
                username=sub_clyde(message.author.name),
                avatar_url=message.author.display_avatar.url,
                wait=True,
            )
        except discord.DiscordException:
            log.exception(
                f"Failed to send message link embed {message.id} to #incidents."
            )
        else:
            await self.message_link_embeds_cache.set(message.id, webhook_msg.id)
            log.trace("Message link embeds sent successfully to #incidents!")
            return webhook_msg.id

    async def delete_msg_link_embed(self, message_id: int) -> None:
        """Delete the Discord message link message found in cache for `message_id`."""
        log.trace("Deleting Discord message link's webhook message.")
        webhook_msg_id = await self.message_link_embeds_cache.get(int(message_id))

        if webhook_msg_id:
            try:
                await self.incidents_webhook.delete_message(webhook_msg_id)
            except discord.errors.NotFound:
                log.trace(f"Incidents message link embed (`{webhook_msg_id}`) has already been deleted, skipping.")

        await self.message_link_embeds_cache.delete(message_id)
        log.trace("Successfully deleted discord links webhook message.")


async def setup(bot: Bot) -> None:
    """Load the Incidents cog."""
    await bot.add_cog(Incidents(bot))
