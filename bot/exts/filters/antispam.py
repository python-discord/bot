import asyncio
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from itertools import takewhile
from operator import attrgetter, itemgetter
from typing import Dict, Iterable, List, Set

import arrow
from botcore.utils import scheduling
from discord import Colour, Member, Message, NotFound, Object, TextChannel
from discord.ext.commands import Cog

from bot import rules
from bot.bot import Bot
from bot.constants import (
    AntiSpam as AntiSpamConfig, Channels, Colours, DEBUG_MODE, Event, Filter, Guild as GuildConfig, Icons
)
from bot.converters import Duration
from bot.exts.events.code_jams._channels import CATEGORY_NAME as JAM_CATEGORY_NAME
from bot.exts.moderation.modlog import ModLog
from bot.log import get_logger
from bot.utils import lock
from bot.utils.message_cache import MessageCache
from bot.utils.messages import format_user, send_attachments

log = get_logger(__name__)

RULE_FUNCTION_MAPPING = {
    'attachments': rules.apply_attachments,
    'burst': rules.apply_burst,
    # burst shared is temporarily disabled due to a bug
    # 'burst_shared': rules.apply_burst_shared,
    'chars': rules.apply_chars,
    'discord_emojis': rules.apply_discord_emojis,
    'duplicates': rules.apply_duplicates,
    'links': rules.apply_links,
    'mentions': rules.apply_mentions,
    'newlines': rules.apply_newlines,
    'role_mentions': rules.apply_role_mentions,
}


@dataclass
class DeletionContext:
    """Represents a Deletion Context for a single spam event."""

    members: frozenset[Member]
    triggered_in: TextChannel
    channels: set[TextChannel] = field(default_factory=set)
    rules: Set[str] = field(default_factory=set)
    messages: Dict[int, Message] = field(default_factory=dict)
    attachments: List[List[str]] = field(default_factory=list)

    async def add(self, rule_name: str, channels: Iterable[TextChannel], messages: Iterable[Message]) -> None:
        """Adds new rule violation events to the deletion context."""
        self.rules.add(rule_name)

        self.channels.update(channels)

        for message in messages:
            if message.id not in self.messages:
                self.messages[message.id] = message

                # Re-upload attachments
                destination = message.guild.get_channel(Channels.attachment_log)
                urls = await send_attachments(message, destination, link_large=False)
                self.attachments.append(urls)

    async def upload_messages(self, actor_id: int, modlog: ModLog) -> None:
        """Method that takes care of uploading the queue and posting modlog alert."""
        triggered_by_users = ", ".join(format_user(m) for m in self.members)
        triggered_in_channel = f"**Triggered in:** {self.triggered_in.mention}\n" if len(self.channels) > 1 else ""
        channels_description = ", ".join(channel.mention for channel in self.channels)

        mod_alert_message = (
            f"**Triggered by:** {triggered_by_users}\n"
            f"{triggered_in_channel}"
            f"**Channels:** {channels_description}\n"
            f"**Rules:** {', '.join(rule for rule in self.rules)}\n"
        )

        messages_as_list = list(self.messages.values())
        first_message = messages_as_list[0]
        # For multiple messages and those with attachments or excessive newlines, use the logs API
        if any((
            len(messages_as_list) > 1,
            len(first_message.attachments) > 0,
            first_message.content.count('\n') > 15
        )):
            url = await modlog.upload_log(self.messages.values(), actor_id, self.attachments)
            mod_alert_message += f"A complete log of the offending messages can be found [here]({url})"
        else:
            mod_alert_message += "Message:\n"
            content = first_message.clean_content
            remaining_chars = 4080 - len(mod_alert_message)

            if len(content) > remaining_chars:
                url = await modlog.upload_log([first_message], actor_id, self.attachments)
                log_site_msg = f"The full message can be found [here]({url})"
                content = content[:remaining_chars - (3 + len(log_site_msg))] + "..."

            mod_alert_message += content

        await modlog.send_log_message(
            content=", ".join(str(m.id) for m in self.members),  # quality-of-life improvement for mobile moderators
            icon_url=Icons.filtering,
            colour=Colour(Colours.soft_red),
            title="Spam detected!",
            text=mod_alert_message,
            thumbnail=first_message.author.display_avatar.url,
            channel_id=Channels.mod_alerts,
            ping_everyone=AntiSpamConfig.ping_everyone
        )


class AntiSpam(Cog):
    """Cog that controls our anti-spam measures."""

    def __init__(self, bot: Bot, validation_errors: Dict[str, str]) -> None:
        self.bot = bot
        self.validation_errors = validation_errors
        role_id = AntiSpamConfig.punishment['role_id']
        self.muted_role = Object(role_id)
        self.expiration_date_converter = Duration()

        self.message_deletion_queue = dict()

        # Fetch the rule configuration with the highest rule interval.
        max_interval_config = max(
            AntiSpamConfig.rules.values(),
            key=itemgetter('interval')
        )
        self.max_interval = max_interval_config['interval']
        self.cache = MessageCache(AntiSpamConfig.cache_size, newest_first=True)

        scheduling.create_task(
            self.alert_on_validation_error(),
            name="AntiSpam.alert_on_validation_error",
            event_loop=self.bot.loop,
        )

    @property
    def mod_log(self) -> ModLog:
        """Allows for easy access of the ModLog cog."""
        return self.bot.get_cog("ModLog")

    async def alert_on_validation_error(self) -> None:
        """Unloads the cog and alerts admins if configuration validation failed."""
        await self.bot.wait_until_guild_available()
        if self.validation_errors:
            body = "**The following errors were encountered:**\n"
            body += "\n".join(f"- {error}" for error in self.validation_errors.values())
            body += "\n\n**The cog has been unloaded.**"

            await self.mod_log.send_log_message(
                title="Error: AntiSpam configuration validation failed!",
                text=body,
                ping_everyone=True,
                icon_url=Icons.token_removed,
                colour=Colour.red()
            )

            self.bot.remove_cog(self.__class__.__name__)
            return

    @Cog.listener()
    async def on_message(self, message: Message) -> None:
        """Applies the antispam rules to each received message."""
        if (
            not message.guild
            or message.guild.id != GuildConfig.id
            or message.author.bot
            or (getattr(message.channel, "category", None) and message.channel.category.name == JAM_CATEGORY_NAME)
            or (message.channel.id in Filter.channel_whitelist and not DEBUG_MODE)
            or (any(role.id in Filter.role_whitelist for role in message.author.roles) and not DEBUG_MODE)
        ):
            return

        self.cache.append(message)

        earliest_relevant_at = arrow.utcnow() - timedelta(seconds=self.max_interval)
        relevant_messages = list(takewhile(lambda msg: msg.created_at > earliest_relevant_at, self.cache))

        for rule_name in AntiSpamConfig.rules:
            rule_config = AntiSpamConfig.rules[rule_name]
            rule_function = RULE_FUNCTION_MAPPING[rule_name]

            # Create a list of messages that were sent in the interval that the rule cares about.
            latest_interesting_stamp = arrow.utcnow() - timedelta(seconds=rule_config['interval'])
            messages_for_rule = list(
                takewhile(lambda msg: msg.created_at > latest_interesting_stamp, relevant_messages)
            )

            result = await rule_function(message, messages_for_rule, rule_config)

            # If the rule returns `None`, that means the message didn't violate it.
            # If it doesn't, it returns a tuple in the form `(str, Iterable[discord.Member])`
            # which contains the reason for why the message violated the rule and
            # an iterable of all members that violated the rule.
            if result is not None:
                self.bot.stats.incr(f"mod_alerts.{rule_name}")
                reason, members, relevant_messages = result
                full_reason = f"`{rule_name}` rule: {reason}"

                # If there's no spam event going on for this channel, start a new Message Deletion Context
                authors_set = frozenset(members)
                if authors_set not in self.message_deletion_queue:
                    log.trace(f"Creating queue for members `{authors_set}`")
                    self.message_deletion_queue[authors_set] = DeletionContext(authors_set, message.channel)
                    scheduling.create_task(
                        self._process_deletion_context(authors_set),
                        name=f"AntiSpam._process_deletion_context({authors_set})"
                    )

                # Add the relevant of this trigger to the Deletion Context
                await self.message_deletion_queue[authors_set].add(
                    rule_name=rule_name,
                    channels=set(message.channel for message in relevant_messages),
                    messages=relevant_messages
                )

                for member in members:
                    scheduling.create_task(
                        self.punish(message, member, full_reason),
                        name=f"AntiSpam.punish(message={message.id}, member={member.id}, rule={rule_name})"
                    )

                await self.maybe_delete_messages(relevant_messages)
                break

    @lock.lock_arg("antispam.punish", "member", attrgetter("id"))
    async def punish(self, msg: Message, member: Member, reason: str) -> None:
        """Punishes the given member for triggering an antispam rule."""
        if not any(role.id == self.muted_role.id for role in member.roles):
            remove_role_after = AntiSpamConfig.punishment['remove_after']

            # Get context and make sure the bot becomes the actor of infraction by patching the `author` attributes
            context = await self.bot.get_context(msg)
            context.author = self.bot.user

            # Since we're going to invoke the tempmute command directly, we need to manually call the converter.
            dt_remove_role_after = await self.expiration_date_converter.convert(context, f"{remove_role_after}S")
            await context.invoke(
                self.bot.get_command('tempmute'),
                member,
                dt_remove_role_after,
                reason=reason
            )

    async def maybe_delete_messages(self, messages: List[Message]) -> None:
        """Cleans the messages if cleaning is configured."""
        if AntiSpamConfig.clean_offending:
            # If we have more than one message, we can use bulk delete.
            if len(messages) > 1:
                message_ids = [message.id for message in messages]
                self.mod_log.ignore(Event.message_delete, *message_ids)
                channel_messages = defaultdict(list)
                for message in messages:
                    channel_messages[message.channel].append(message)
                for channel, messages in channel_messages.items():
                    try:
                        await channel.delete_messages(messages)
                    except NotFound:
                        # In the rare case where we found messages matching the
                        # spam filter across multiple channels, it is possible
                        # that a single channel will only contain a single message
                        # to delete. If that should be the case, discord.py will
                        # use the "delete single message" endpoint instead of the
                        # bulk delete endpoint, and the single message deletion
                        # endpoint will complain if you give it that does not exist.
                        # As this means that we have no other message to delete in
                        # this channel (and message deletes work per-channel),
                        # we can just log an exception and carry on with business.
                        log.info(f"Tried to delete message `{messages[0].id}`, but message could not be found.")

            # Otherwise, the bulk delete endpoint will throw up.
            # Delete the message directly instead.
            else:
                self.mod_log.ignore(Event.message_delete, messages[0].id)
                try:
                    await messages[0].delete()
                except NotFound:
                    log.info(f"Tried to delete message `{messages[0].id}`, but message could not be found.")

    async def _process_deletion_context(self, context_id: frozenset) -> None:
        """Processes the Deletion Context queue."""
        log.trace("Sleeping before processing message deletion queue.")
        await asyncio.sleep(10)

        if context_id not in self.message_deletion_queue:
            log.error(f"Started processing deletion queue for context `{context_id}`, but it was not found!")
            return

        deletion_context = self.message_deletion_queue.pop(context_id)
        await deletion_context.upload_messages(self.bot.user.id, self.mod_log)

    @Cog.listener()
    async def on_message_edit(self, before: Message, after: Message) -> None:
        """Updates the message in the cache, if it's cached."""
        self.cache.update(after)


def validate_config(rules_: Mapping = AntiSpamConfig.rules) -> Dict[str, str]:
    """Validates the antispam configs."""
    validation_errors = {}
    for name, config in rules_.items():
        if name not in RULE_FUNCTION_MAPPING:
            log.error(
                f"Unrecognized antispam rule `{name}`. "
                f"Valid rules are: {', '.join(RULE_FUNCTION_MAPPING)}"
            )
            validation_errors[name] = f"`{name}` is not recognized as an antispam rule."
            continue
        for required_key in ('interval', 'max'):
            if required_key not in config:
                log.error(
                    f"`{required_key}` is required but was not "
                    f"set in rule `{name}`'s configuration."
                )
                validation_errors[name] = f"Key `{required_key}` is required but not set for rule `{name}`"
    return validation_errors


def setup(bot: Bot) -> None:
    """Validate the AntiSpam configs and load the AntiSpam cog."""
    validation_errors = validate_config()
    bot.add_cog(AntiSpam(bot, validation_errors))
