from __future__ import annotations

import typing
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass, field, replace as dataclass_replace
from enum import Enum, auto

import discord
from discord import DMChannel, Embed, Member, Message, StageChannel, TextChannel, Thread, User, VoiceChannel

from bot.utils.message_cache import MessageCache

if typing.TYPE_CHECKING:
    from bot.exts.filtering._filter_lists import FilterList
    from bot.exts.filtering._filters.filter import Filter
    from bot.exts.utils.snekbox._io import FileAttachment


class Event(Enum):
    """Types of events that can trigger filtering. Note this does not have to align with gateway event types."""

    MESSAGE = auto()
    MESSAGE_EDIT = auto()
    NICKNAME = auto()
    THREAD_NAME = auto()
    SNEKBOX = auto()


@dataclass
class FilterSource:
    """The source/sender metadata for a filtering context."""

    event: Event
    author: User | Member | None
    channel: TextChannel | VoiceChannel | StageChannel | Thread | DMChannel | None
    message: Message | None
    before_message: Message | None = None
    message_cache: MessageCache | None = None


@dataclass
class FilterContent:
    """The content being filtered."""

    content: str | Iterable
    embeds: list[Embed] = field(default_factory=list)
    attachments: list[discord.Attachment | FileAttachment] = field(default_factory=list)


@dataclass
class FilterNotifications:
    """DM and alert content produced by filtering."""

    dm_content: str = ""
    dm_embed: str = ""
    send_alert: bool = False
    alert_content: str = ""
    alert_embeds: list[Embed] = field(default_factory=list)
    notification_domain: str = ""
    action_descriptions: list[str] = field(default_factory=list)


@dataclass
class FilterActions:
    """Side effects and deletion metadata produced by filtering."""

    additional_actions: list[Callable[[FilterContext], Coroutine]] = field(default_factory=list)
    messages_deletion: bool = False
    related_messages: set[Message] = field(default_factory=set)
    related_channels: set[TextChannel | Thread | DMChannel] = field(default_factory=set)
    uploaded_attachments: dict[int, list[str]] = field(default_factory=dict)
    upload_deletion_logs: bool = True


@dataclass
class FilterResults:
    """Filter match results and tracking data."""

    matches: list[str] = field(default_factory=list)
    filter_info: dict[Filter, str] = field(default_factory=dict)
    blocked_exts: set[str] = field(default_factory=set)
    potential_phish: dict[FilterList, set[str]] = field(default_factory=dict)


class FilterContext:
    """A context object containing the information that should be filtered, and output information of the filtering.

    Attributes are delegated to sub-objects for organization:
    - ``source``: event, author, channel, message, before_message, message_cache
    - ``content``: content, embeds, attachments
    - ``notifications``: dm_content, dm_embed, send_alert, alert_content, alert_embeds, notification_domain, action_descriptions
    - ``actions``: additional_actions, messages_deletion, related_messages, related_channels, uploaded_attachments, upload_deletion_logs
    - ``results``: matches, filter_info, blocked_exts, potential_phish
    """

    def __init__(self, source, content, notifications=None, actions=None, results=None):
        self._source = source
        self._content = content
        self._notifications = notifications or FilterNotifications()
        self._actions = actions or FilterActions()
        self._results = results or FilterResults()
        self.in_guild = source.channel is None or source.channel.guild is not None

    def __getattr__(self, name):
        for obj in (self._source, self._content, self._notifications, self._actions, self._results):
            if hasattr(obj, name):
                return getattr(obj, name)
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

    def __setattr__(self, name, value):
        if name.startswith('_') or name == 'in_guild':
            object.__setattr__(self, name, value)
            return
        for obj in (self._source, self._content, self._notifications, self._actions, self._results):
            if hasattr(obj, name):
                setattr(obj, name, value)
                return
        object.__setattr__(self, name, value)

    @classmethod
    def from_message(
        cls, event: Event, message: Message, before: Message | None = None, cache: MessageCache | None = None
    ) -> FilterContext:
        """Create a filtering context from the attributes of a message."""
        source = FilterSource(event, message.author, message.channel, message, before, cache)
        content = FilterContent(message.content, message.embeds, message.attachments)
        return cls(source, content)

    def replace(self, **changes) -> FilterContext:
        """Return a new context object assigning new values to the specified fields."""
        sub_objects = {
            '_source': self._source,
            '_content': self._content,
            '_notifications': self._notifications,
            '_actions': self._actions,
            '_results': self._results,
        }
        sub_changes = {}
        for key, value in changes.items():
            for attr_name, obj in sub_objects.items():
                if hasattr(obj, key):
                    sub_changes.setdefault(attr_name, {})[key] = value
                    break
        return FilterContext(
            source=dataclass_replace(self._source, **sub_changes.get('_source', {})),
            content=dataclass_replace(self._content, **sub_changes.get('_content', {})),
            notifications=dataclass_replace(self._notifications, **sub_changes.get('_notifications', {})),
            actions=dataclass_replace(self._actions, **sub_changes.get('_actions', {})),
            results=dataclass_replace(self._results, **sub_changes.get('_results', {})),
        )
