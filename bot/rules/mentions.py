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
    # We use `msg.mentions` here as that is supplied by the api itself, to determine who was mentioned
    # Additionally, `msg.mentions` includes the user replied to, even if the mention doesn't occur in the body.
    # In order to exclude users who are mentioned as a reply, we check if the msg has a reference
    #
    # While we could use regex to parse the message content, and get a list of
    # the mentions, that solution is very prone to breaking.
    # We would need to deal with codeblocks, escaping markdown, and any discrepancies between
    # our implementation and discord's markdown parser which would cause false positives or false negatives.
    total_recent_mentions = sum(
        not (user.bot or msg.author == user)
        for msg in relevant_messages
        for user in msg.mentions
    )

    # no reason to run processing and fetch messages if there are no mentions.
    if not total_recent_mentions:
        return None

    # we don't want to include mentions that are to the replied user in message replies.
    for msg in relevant_messages:

        if msg.type != MessageType.reply and not msg.reference:
            continue

        resolved = msg.reference.resolved
        if isinstance(resolved, DeletedReferencedMessage):
            # can't figure out the author
            continue

        if not resolved:
            ref = msg.reference
            # it is possible, in a very unusual situation, for a message to have a reference
            # that is both not in the cache, and deleted while running this function.
            # in such a situation this will throw an error.
            try:
                resolved = await bot.instance.get_partial_messageable(ref.channel_id).fetch_message(ref.message_id)
            except NotFound:
                log.info('Could not fetch the replied reference as its been deleted.')
                continue
        # the rule ignores the potential mention from replying to a message.
        # we first check if the reply was to a bot or the author since those mentions are already ignored above.
        if not (resolved.author.bot or resolved.author == msg.author) and resolved.author in msg.mentions:
            total_recent_mentions -= 1

        # break the loop once `total_recent_mentions` reaches zero
        if not total_recent_mentions:
            break

    if total_recent_mentions > config['max']:
        return (
            f"sent {total_recent_mentions} mentions in {config['interval']}s",
            (last_message.author,),
            relevant_messages
        )
    return None
