from datetime import timedelta
from itertools import takewhile
from typing import ClassVar

import arrow
from discord import DeletedReferencedMessage, MessageType, NotFound
from pydantic import BaseModel
from pydis_core.utils.logging import get_logger

import bot
from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filters.filter import UniqueFilter

log = get_logger(__name__)


class ExtraMentionsSettings(BaseModel):
    """Extra settings for when to trigger the antispam rule."""

    interval_description: ClassVar[str] = (
        "Look for rule violations in messages from the last `interval` number of seconds."
    )
    threshold_description: ClassVar[str] = "Maximum number of distinct mentions before the filter is triggered."

    interval: int = 10
    threshold: int = 5


class MentionsFilter(UniqueFilter):
    """
    Detects total mentions exceeding the limit sent by a single user.

    Excludes mentions that are bots, themselves, or replied users.

    In very rare cases, may not be able to determine a
    mention was to a reply, in which case it is not ignored.
    """

    name = "mentions"
    events = (Event.MESSAGE,)
    extra_fields_type = ExtraMentionsSettings

    async def triggered_on(self, ctx: FilterContext) -> bool:
        """Search for the filter's content within a given context."""
        earliest_relevant_at = arrow.utcnow() - timedelta(seconds=self.extra_fields.interval)
        relevant_messages = list(takewhile(lambda msg: msg.created_at > earliest_relevant_at, ctx.content))
        detected_messages = {msg for msg in relevant_messages if msg.author == ctx.author}

        # We use `msg.mentions` here as that is supplied by the api itself, to determine who was mentioned.
        # Additionally, `msg.mentions` includes the user replied to, even if the mention doesn't occur in the body.
        # In order to exclude users who are mentioned as a reply, we check if the msg has a reference
        #
        # While we could use regex to parse the message content, and get a list of
        # the mentions, that solution is very prone to breaking.
        # We would need to deal with codeblocks, escaping markdown, and any discrepancies between
        # our implementation and discord's Markdown parser which would cause false positives or false negatives.
        total_recent_mentions = 0
        for msg in detected_messages:
            # We check if the message is a reply, and if it is try to get the author
            # since we ignore mentions of a user that we're replying to
            reply_author = None

            if msg.type == MessageType.reply:
                ref = msg.reference

                if not (resolved := ref.resolved):
                    # It is possible, in a very unusual situation, for a message to have a reference
                    # that is both not in the cache, and deleted while running this function.
                    # In such a situation, this will throw an error which we catch.
                    try:
                        resolved = await bot.instance.get_partial_messageable(resolved.channel_id).fetch_message(
                            resolved.message_id
                        )
                    except NotFound:
                        log.info("Could not fetch the reference message as it has been deleted.")

                if resolved and not isinstance(resolved, DeletedReferencedMessage):
                    reply_author = resolved.author

            for user in msg.mentions:
                # Don't count bot or self mentions, or the user being replied to (if applicable)
                if user.bot or user in {msg.author, reply_author}:
                    continue
                total_recent_mentions += 1

        if total_recent_mentions > self.extra_fields.threshold:
            ctx.related_messages |= detected_messages
            ctx.filter_info[self] = f"sent {total_recent_mentions} mentions"
            return True
        return False
