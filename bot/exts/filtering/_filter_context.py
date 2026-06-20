import typing
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass, field, replace
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
class FilterInput:  # pylint: disable=too-many-instance-attributes
    """Input data for filtering: event details and message content."""

    event: Event
    author: User | Member | None
    channel: TextChannel | VoiceChannel | StageChannel | Thread | DMChannel | None
    content: str | Iterable
    message: Message | None
    embeds: list[Embed] = field(default_factory=list)
    attachments: list[discord.Attachment | FileAttachment] = field(default_factory=list)
    before_message: Message | None = None
    message_cache: MessageCache | None = None


@dataclass
class FilterOutput:  # pylint: disable=too-many-instance-attributes
    """Output data produced by filtering: alerts, actions, and results."""

    dm_content: str = ""
    dm_embed: str = ""
    send_alert: bool = False
    alert_content: str = ""
    alert_embeds: list[Embed] = field(default_factory=list)
    action_descriptions: list[str] = field(default_factory=list)
    matches: list[str] = field(default_factory=list)
    notification_domain: str = ""
    filter_info: dict[Filter, str] = field(default_factory=dict)
    messages_deletion: bool = False
    blocked_exts: set[str] = field(default_factory=set)
    potential_phish: dict[FilterList, set[str]] = field(default_factory=dict)


_FILTER_CONTEXT_DIRECT_FIELDS = frozenset({
    'input', 'output', 'additional_actions', 'related_messages',
    'related_channels', 'uploaded_attachments', 'upload_deletion_logs',
})


@dataclass
class FilterContext:
    """A dataclass containing the information that should be filtered, and output information of the filtering."""

    input: FilterInput
    output: FilterOutput
    additional_actions: list[Callable[[FilterContext], Coroutine]] = field(default_factory=list)
    related_messages: set[Message] = field(default_factory=set)
    related_channels: set[TextChannel | Thread | DMChannel] = field(default_factory=set)
    uploaded_attachments: dict[int, list[str]] = field(default_factory=dict)
    upload_deletion_logs: bool = True

    @property
    def in_guild(self) -> bool:
        """Whether the context is from a guild channel (not a DM)."""
        return self.input.channel is None or self.input.channel.guild is not None

    def __getattr__(self, name):
        try:
            input_obj = object.__getattribute__(self, 'input')
            if hasattr(input_obj, name):
                return getattr(input_obj, name)
        except AttributeError:
            pass
        try:
            output_obj = object.__getattribute__(self, 'output')
            if hasattr(output_obj, name):
                return getattr(output_obj, name)
        except AttributeError:
            pass
        raise AttributeError(f"'FilterContext' has no attribute '{name}'")

    def __setattr__(self, name, value):
        if name in _FILTER_CONTEXT_DIRECT_FIELDS:
            object.__setattr__(self, name, value)
            return
        try:
            input_obj = object.__getattribute__(self, 'input')
            if hasattr(input_obj, name):
                setattr(input_obj, name, value)
                return
        except AttributeError:
            pass
        try:
            output_obj = object.__getattribute__(self, 'output')
            if hasattr(output_obj, name):
                setattr(output_obj, name, value)
                return
        except AttributeError:
            pass
        object.__setattr__(self, name, value)

    @classmethod
    def from_message(
        cls, event: Event, message: Message, before: Message | None = None, cache: MessageCache | None = None
    ) -> FilterContext:
        """Create a filtering context from the attributes of a message."""
        return cls(
            FilterInput(
                event,
                message.author,
                message.channel,
                message.content,
                message,
                message.embeds,
                message.attachments,
                before,
                cache
            ),
            FilterOutput()
        )

    def replace(self, **changes) -> FilterContext:
        """Return a new context object assigning new values to the specified fields."""
        input_fields = FilterInput.__dataclass_fields__
        output_fields = FilterOutput.__dataclass_fields__
        input_changes = {}
        output_changes = {}
        context_changes = {}
        for k, v in changes.items():
            if k in input_fields:
                input_changes[k] = v
            elif k in output_fields:
                output_changes[k] = v
            else:
                context_changes[k] = v
        new_input = replace(self.input, **input_changes) if input_changes else self.input
        new_output = replace(self.output, **output_changes) if output_changes else self.output
        return FilterContext(new_input, new_output, **context_changes)
