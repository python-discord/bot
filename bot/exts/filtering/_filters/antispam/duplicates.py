from datetime import timedelta
from itertools import takewhile
from typing import ClassVar

import arrow
from pydantic import BaseModel

from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filters.filter import UniqueFilter


class ExtraDuplicatesSettings(BaseModel):
    """Extra settings for when to trigger the antispam rule."""

    interval_description: ClassVar[str] = (
        "Look for rule violations in messages from the last `interval` number of seconds."
    )
    threshold_description: ClassVar[str] = "Maximum number of duplicate messages before the filter is triggered."

    interval: int = 10
    threshold: int = 3


class DuplicatesFilter(UniqueFilter):
    """Detects duplicated messages sent by a single user."""

    name = "duplicates"
    events = (Event.MESSAGE,)
    extra_fields_type = ExtraDuplicatesSettings

    async def triggered_on(self, ctx: FilterContext) -> bool:
        """Search for the filter's content within a given context."""
        earliest_relevant_at = arrow.utcnow() - timedelta(seconds=self.extra_fields.interval)
        relevant_messages = list(takewhile(lambda msg: msg.created_at > earliest_relevant_at, ctx.content))

        detected_messages = {
            msg for msg in relevant_messages
            if msg.author == ctx.author and msg.content == ctx.message.content and msg.content
        }
        if len(detected_messages) > self.extra_fields.threshold:
            ctx.related_messages |= detected_messages
            ctx.filter_info[self] = f"sent {len(detected_messages)} duplicate messages"
            return True
        return False
