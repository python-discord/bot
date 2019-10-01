import re
from typing import Dict, Iterable, List, Optional, Tuple

from discord import Member, Message


DISCORD_EMOJI_RE = re.compile(r"<:\w+:\d+>")


async def apply(
    last_message: Message, recent_messages: List[Message], config: Dict[str, int]
) -> Optional[Tuple[str, Iterable[Member], Iterable[Message]]]:
    """Detects total Discord emojis (excluding Unicode emojis) exceeding the limit sent by a single user."""
    relevant_messages = tuple(
        msg
        for msg in recent_messages
        if msg.author == last_message.author
    )

    total_emojis = sum(
        len(DISCORD_EMOJI_RE.findall(msg.content))
        for msg in relevant_messages
    )

    if total_emojis > config['max']:
        return (
            f"sent {total_emojis} emojis in {config['interval']}s",
            (last_message.author,),
            relevant_messages
        )
    return None
