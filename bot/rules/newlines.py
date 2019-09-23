import re
from typing import Dict, Iterable, List, Optional, Tuple

from discord import Member, Message


async def apply(
    last_message: Message, recent_messages: List[Message], config: Dict[str, int]
) -> Optional[Tuple[str, Iterable[Member], Iterable[Message]]]:
    """Detects total newlines exceeding the set limit sent by a single user."""
    relevant_messages = tuple(
        msg
        for msg in recent_messages
        if msg.author == last_message.author
    )

    # Identify groups of newline characters and get group & total counts
    exp = r"(\n+)"
    newline_counts = []
    for msg in relevant_messages:
        newline_counts += [len(group) for group in re.findall(exp, msg.content)]
    total_recent_newlines = sum(newline_counts)

    # Get maximum newline group size
    if newline_counts:
        max_newline_group = max(newline_counts)
    else:
        # If no newlines are found, newline_counts will be an empty list, which will error out max()
        max_newline_group = 0

    # Check first for total newlines, if this passes then check for large groupings
    if total_recent_newlines > config['max']:
        return (
            f"sent {total_recent_newlines} newlines in {config['interval']}s",
            (last_message.author,),
            relevant_messages
        )
    elif max_newline_group > config['max_consecutive']:
        return (
            f"sent {max_newline_group} consecutive newlines in {config['interval']}s",
            (last_message.author,),
            relevant_messages
        )

    return None
