from typing import Dict, Iterable, List, Optional, Tuple

from discord import Member, Message

from bot.constants import Channels


async def apply(
    last_message: Message, recent_messages: List[Message], config: Dict[str, int]
) -> Optional[Tuple[str, Iterable[Member], Iterable[Message]]]:
    """
    Detects repeated messages sent by multiple users.

    This filter never triggers in the verification channel.
    """
    if last_message.channel.id == Channels.verification:
        return

    total_recent = len(recent_messages)

    if total_recent > config['max']:
        return (
            f"sent {total_recent} messages in {config['interval']}s",
            set(msg.author for msg in recent_messages),
            recent_messages
        )
    return None
