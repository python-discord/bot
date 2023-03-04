from __future__ import annotations

import typing
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass, field, replace
from enum import Enum, auto

from discord import DMChannel, Embed, Member, Message, TextChannel, Thread, User

from bot.utils.message_cache import MessageCache

if typing.TYPE_CHECKING:
    from bot.exts.filtering._filters.filter import Filter


class Event(Enum):
    """Types of events that can trigger filtering. Note this does not have to align with gateway event types."""

    MESSAGE = auto()
    MESSAGE_EDIT = auto()
    NICKNAME = auto()


@dataclass
class FilterContext:
    """A dataclass containing the information that should be filtered, and output information of the filtering."""

    # Input context
    event: Event  # The type of event
    author: User | Member | None  # Who triggered the event
    channel: TextChannel | Thread | DMChannel | None  # The channel involved
    content: str | Iterable  # What actually needs filtering. The Iterable type depends on the filter list.
    message: Message | None  # The message involved
    embeds: list[Embed] = field(default_factory=list)  # Any embeds involved
    before_message: Message | None = None
    message_cache: MessageCache | None = None
    # Output context
    dm_content: str = ""  # The content to DM the invoker
    dm_embed: str = ""  # The embed description to DM the invoker
    send_alert: bool = False  # Whether to send an alert for the moderators
    alert_content: str = ""  # The content of the alert
    alert_embeds: list[Embed] = field(default_factory=list)  # Any embeds to add to the alert
    action_descriptions: list[str] = field(default_factory=list)  # What actions were taken
    matches: list[str] = field(default_factory=list)  # What exactly was found
    notification_domain: str = ""  # A domain to send the user for context
    filter_info: dict['Filter', str] = field(default_factory=dict)  # Additional info from a filter.
    messages_deletion: bool = False  # Whether the messages were deleted. Can't upload deletion log otherwise.
    # Additional actions to perform
    additional_actions: list[Callable[[FilterContext], Coroutine]] = field(default_factory=list)
    related_messages: set[Message] = field(default_factory=set)  # Deletion will include these.
    related_channels: set[TextChannel | Thread | DMChannel] = field(default_factory=set)
    attachments: dict[int, list[str]] = field(default_factory=dict)  # Message ID to attachment URLs.
    upload_deletion_logs: bool = True  # Whether it's allowed to upload deletion logs.

    @classmethod
    def from_message(
        cls, event: Event, message: Message, before: Message | None = None, cache: MessageCache | None = None
    ) -> FilterContext:
        """Create a filtering context from the attributes of a message."""
        return cls(event, message.author, message.channel, message.content, message, message.embeds, before, cache)

    def replace(self, **changes) -> FilterContext:
        """Return a new context object assigning new values to the specified fields."""
        return replace(self, **changes)
