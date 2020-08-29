from typing import Dict, Iterable, List, Optional, Tuple

from discord import Member, Message


async def apply(
    last_message: Message,
    recent_messages: List[Message],
    config: Dict[str, int],
) -> Optional[Tuple[str, Iterable[Member], Iterable[Message]]]:
    """Detects if a user has sent an '@everyone' ping."""
    relevant_messages = tuple(
        msg for msg in recent_messages if msg.author == last_message.author
    )

    ev_msgs_ct = 0
    if config["max"]:
        for msg in relevant_messages:
            ev_role = msg.guild.default_role
            msg_roles = msg.role_mentions

            if ev_role in msg_roles:
                ev_msgs_ct += 1

    if ev_msgs_ct > 0:
        return (
            f"pinged the everyone role {ev_msgs_ct} times",
            (last_message.author),
            relevant_messages,
        )
    return None
