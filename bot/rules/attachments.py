from typing import Dict, Iterable, List, Optional, Tuple

from discord import Member, Message


async def apply(
    last_message: Message, recent_messages: List[Message], config: Dict[str, int]
) -> Optional[Tuple[str, Iterable[Member], Iterable[Message]]]:
    """Detects total attachments exceeding the limit sent by a single user."""
    relevant_messages = tuple(
        msg
        for msg in recent_messages
        if (
            msg.author == last_message.author
            and len(msg.attachments) > 0
        )
    )
    total_recent_attachments = sum(len(msg.attachments) for msg in relevant_messages)

    if total_recent_attachments > config['max']:
        return (
            f"sent {total_recent_attachments} attachments in {config['interval']}s",
            (last_message.author,),
            relevant_messages
        )
    return None
