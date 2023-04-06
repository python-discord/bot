import re
from datetime import timedelta
from itertools import takewhile
from typing import ClassVar

import arrow
from emoji import demojize
from pydantic import BaseModel

from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filters.filter import UniqueFilter

DISCORD_EMOJI_RE = re.compile(r"<:\w+:\d+>|:\w+:")
CODE_BLOCK_RE = re.compile(r"```.*?```", flags=re.DOTALL)


class ExtraEmojiSettings(BaseModel):
    """Extra settings for when to trigger the antispam rule."""

    interval_description: ClassVar[str] = (
        "Look for rule violations in messages from the last `interval` number of seconds."
    )
    threshold_description: ClassVar[str] = "Maximum number of emojis before the filter is triggered."

    interval: int = 10
    threshold: int = 20


class EmojiFilter(UniqueFilter):
    """Detects too many emojis sent by a single user."""

    name = "emoji"
    events = (Event.MESSAGE,)
    extra_fields_type = ExtraEmojiSettings

    async def triggered_on(self, ctx: FilterContext) -> bool:
        """Search for the filter's content within a given context."""
        earliest_relevant_at = arrow.utcnow() - timedelta(seconds=self.extra_fields.interval)
        relevant_messages = list(takewhile(lambda msg: msg.created_at > earliest_relevant_at, ctx.content))
        detected_messages = {msg for msg in relevant_messages if msg.author == ctx.author}

        # Get rid of code blocks in the message before searching for emojis.
        # Convert Unicode emojis to :emoji: format to get their count.
        total_emojis = sum(
            len(DISCORD_EMOJI_RE.findall(demojize(CODE_BLOCK_RE.sub("", msg.content))))
            for msg in detected_messages
        )

        if total_emojis > self.extra_fields.threshold:
            ctx.related_messages |= detected_messages
            ctx.filter_info[self] = f"sent {total_emojis} emojis"
            return True
        return False
