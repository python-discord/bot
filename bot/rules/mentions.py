from typing import Dict, Iterable, List, Optional, Tuple

from discord import DeletedReferencedMessage, Member, Message

import bot


async def apply(
    last_message: Message, recent_messages: List[Message], config: Dict[str, int]
) -> Optional[Tuple[str, Iterable[Member], Iterable[Message]]]:
    """Detects total mentions exceeding the limit sent by a single user."""
    relevant_messages = tuple(
        msg
        for msg in recent_messages
        if msg.author == last_message.author
    )

    total_recent_mentions = sum(
        not user.bot
        and msg.author.id != user.id
        for msg in relevant_messages
        for user in msg.mentions
    )

    # we don't want to include the mentions that the author mentioned with a reply
    total_recent_mentions = 0
    for msg in relevant_messages:
        if not msg.reference:
            continue
        resolved = msg.reference.resolved
        if isinstance(resolved, DeletedReferencedMessage):
            # can't figure out the author
            continue
        if not resolved:
            ref = msg.reference
            resolved = await bot.instance.get_partial_messageable(ref.channel_id).fetch_message(ref.message_id)
        if resolved.author in msg.mentions:
            total_recent_mentions -= 1

    if total_recent_mentions > config['max']:
        return (
            f"sent {total_recent_mentions} mentions in {config['interval']}s",
            (last_message.author,),
            relevant_messages
        )
    return None
