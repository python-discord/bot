from typing import Dict, Iterable, List, Optional, Tuple

from discord import DeletedReferencedMessage, Member, Message, MessageType, NotFound

import bot
from bot.log import get_logger

log = get_logger(__name__)


async def apply(
    last_message: Message, recent_messages: List[Message], config: Dict[str, int]
) -> Optional[Tuple[str, Iterable[Member], Iterable[Message]]]:
    """
    Detects total mentions exceeding the limit sent by a single user.

    Excludes mentions that are bots, themselves, or replied users.

    In very rare cases, may not be able to determine a
    mention was to a reply, in which case it is not ignored.
    """
    relevant_messages = tuple(
        msg
        for msg in recent_messages
        if msg.author == last_message.author
    )
    # We use `msg.mentions` here as that is supplied by the api itself, to determine who was mentioned.
    # Additionally, `msg.mentions` includes the user replied to, even if the mention doesn't occur in the body.
    # In order to exclude users who are mentioned as a reply, we check if the msg has a reference
    #
    # While we could use regex to parse the message content, and get a list of
    # the mentions, that solution is very prone to breaking.
    # We would need to deal with codeblocks, escaping markdown, and any discrepancies between
    # our implementation and discord's markdown parser which would cause false positives or false negatives.
    total_recent_mentions = 0
    for msg in relevant_messages:
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
                    log.info('Could not fetch the reference message as it has been deleted.')

            if resolved and not isinstance(resolved, DeletedReferencedMessage):
                reply_author = resolved.author

        for user in msg.mentions:
            # Don't count bot or self mentions, or the user being replied to (if applicable)
            if user.bot or user in {msg.author, reply_author}:
                continue
            total_recent_mentions += 1

    if total_recent_mentions > config['max']:
        return (
            f"sent {total_recent_mentions} mentions in {config['interval']}s",
            (last_message.author,),
            relevant_messages
        )
    return None
