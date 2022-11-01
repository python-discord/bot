from datetime import timedelta
from itertools import takewhile
from typing import ClassVar

import arrow
from pydantic import BaseModel

from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filters.filter import UniqueFilter


class ExtraAttachmentsSettings(BaseModel):
    """Extra settings for when to trigger the antispam rule."""

    interval_description: ClassVar[str] = (
        "Look for rule violations in messages from the last `interval` number of seconds."
    )
    threshold_description: ClassVar[str] = "Maximum number of attachments before the filter is triggered."

    interval: int = 10
    threshold: int = 6


class AttachmentsFilter(UniqueFilter):
    """Detects too many attachments sent by a single user."""

    name = "attachments"
    events = (Event.MESSAGE,)
    extra_fields_type = ExtraAttachmentsSettings

    async def triggered_on(self, ctx: FilterContext) -> bool:
        """Search for the filter's content within a given context."""
        earliest_relevant_at = arrow.utcnow() - timedelta(seconds=self.extra_fields.interval)
        relevant_messages = list(takewhile(lambda msg: msg.created_at > earliest_relevant_at, ctx.content))

        detected_messages = {msg for msg in relevant_messages if msg.author == ctx.author and len(msg.attachments) > 0}
        total_recent_attachments = sum(len(msg.attachments) for msg in detected_messages)

        if total_recent_attachments > self.extra_fields.threshold:
            ctx.related_messages |= detected_messages
            ctx.filter_info[self] = f"sent {total_recent_attachments} attachments"
            return True
        return False
