from typing import Dict, Iterable, List, Optional, Tuple

from discord import Member, Message


async def apply(
    last_message: Message, recent_messages: List[Message], config: Dict[str, int]
) -> Optional[Tuple[str, Iterable[Member], Iterable[Message]]]:
    """Detects repeated messages sent by multiple users."""
    total_recent = len(recent_messages)

    if total_recent > config['max']:
        return (
            f"sent {total_recent} messages in {config['interval']}s",
            set(msg.author for msg in recent_messages),
            recent_messages
        )
    return None
