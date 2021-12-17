from typing import Dict, Iterable, List, Optional, Tuple

from discord import DeletedReferencedMessage, Member, Message, MessageType, NotFound

import bot

log = bot.log.get_logger(__name__)


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
    # We use msg.mentions here as that is supplied by the api itself, to determine who was mentioned
    # Additionally, msg.mentions includes the user replied to, even if the mention doesn't occur in the body.
    # In order to exclude users who are mentioned as a reply, we check if the msg has a reference
    #
    # While we could use regex to parse the message content, and get a list of the mentions,
    # that is very prone to breaking, as both the markdown, if discord used it, code block, etc
    total_recent_mentions = sum(
        not user.bot
        and msg.author != user
        for msg in relevant_messages
        for user in msg.mentions
    )

    # we don't want to include the mentions that the author mentioned with a reply
    for msg in relevant_messages:
        # break the loop to save processing if total_recent_mentions is 0
        # additionally, ensures that we don't find a mention that wasn't originally there.
        if not total_recent_mentions:
            break
        if msg.type != MessageType.reply and not msg.reference:
            continue
        resolved = msg.reference.resolved
        if isinstance(resolved, DeletedReferencedMessage):
            # can't figure out the author
            continue
        if not resolved:
            ref = msg.reference
            try:
                # its possible, in a very unusual situation, for a message to have a reference
                # that is both not in the cache, and deleted while running this function.
                resolved = await bot.instance.get_partial_messageable(ref.channel_id).fetch_message(ref.message_id)
            except NotFound:
                log.info('Could not fetch the replied reference as its been deleted.')
                continue
        if resolved.author in msg.mentions:
            total_recent_mentions -= 1

    if total_recent_mentions > config['max']:
        return (
            f"sent {total_recent_mentions} mentions in {config['interval']}s",
            (last_message.author,),
            relevant_messages
        )
    return None
