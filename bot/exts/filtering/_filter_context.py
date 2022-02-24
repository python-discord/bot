from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum, auto
from typing import Optional, Union

from discord import DMChannel, Message, TextChannel, Thread, User


class Event(Enum):
    """Types of events that can trigger filtering. Note this does not have to align with gateway event types."""

    MESSAGE = auto()
    MESSAGE_EDIT = auto()


@dataclass
class FilterContext:
    """A dataclass containing the information that should be filtered, and output information of the filtering."""

    # Input context
    event: Event  # The type of event
    author: User  # Who triggered the event
    channel: Union[TextChannel, Thread, DMChannel]  # The channel involved
    content: Union[str, set[str]]  # What actually needs filtering
    message: Optional[Message]  # The message involved
    embeds: list = field(default_factory=list)  # Any embeds involved
    # Output context
    dm_content: str = field(default_factory=str)  # The content to DM the invoker
    dm_embed: str = field(default_factory=str)  # The embed description to DM the invoker
    send_alert: bool = field(default=True)  # Whether to send an alert for the moderators
    alert_content: str = field(default_factory=str)  # The content of the alert
    alert_embeds: list = field(default_factory=list)  # Any embeds to add to the alert
    action_descriptions: list = field(default_factory=list)  # What actions were taken
    matches: list = field(default_factory=list)  # What exactly was found

    def replace(self, **changes) -> FilterContext:
        """Return a new context object assigning new values to the specified fields."""
        return replace(self, **changes)
