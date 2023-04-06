import re
from datetime import timedelta
from itertools import takewhile
from typing import ClassVar

import arrow
from pydantic import BaseModel

from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filters.filter import UniqueFilter

NEWLINES = re.compile(r"(\n+)")


class ExtraNewlinesSettings(BaseModel):
    """Extra settings for when to trigger the antispam rule."""

    interval_description: ClassVar[str] = (
        "Look for rule violations in messages from the last `interval` number of seconds."
    )
    threshold_description: ClassVar[str] = "Maximum number of newlines before the filter is triggered."
    consecutive_threshold_description: ClassVar[str] = (
        "Maximum number of consecutive newlines before the filter is triggered."
    )

    interval: int = 10
    threshold: int = 100
    consecutive_threshold: int = 10


class NewlinesFilter(UniqueFilter):
    """Detects too many newlines sent by a single user."""

    name = "newlines"
    events = (Event.MESSAGE,)
    extra_fields_type = ExtraNewlinesSettings

    async def triggered_on(self, ctx: FilterContext) -> bool:
        """Search for the filter's content within a given context."""
        earliest_relevant_at = arrow.utcnow() - timedelta(seconds=self.extra_fields.interval)
        relevant_messages = list(takewhile(lambda msg: msg.created_at > earliest_relevant_at, ctx.content))
        detected_messages = {msg for msg in relevant_messages if msg.author == ctx.author}

        # Identify groups of newline characters and get group & total counts
        newline_counts = []
        for msg in detected_messages:
            newline_counts += [len(group) for group in NEWLINES.findall(msg.content)]
        total_recent_newlines = sum(newline_counts)
        # Get maximum newline group size
        max_newline_group = max(newline_counts, default=0)

        # Check first for total newlines, if this passes then check for large groupings
        if total_recent_newlines > self.extra_fields.threshold:
            ctx.related_messages |= detected_messages
            ctx.filter_info[self] = f"sent {total_recent_newlines} newlines"
            return True
        if max_newline_group > self.extra_fields.consecutive_threshold:
            ctx.related_messages |= detected_messages
            ctx.filter_info[self] = f"sent {max_newline_group} consecutive newlines"
            return True
        return False
