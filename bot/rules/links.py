import re
from typing import Dict, Iterable, List, Optional, Tuple

from discord import Member, Message


LINK_RE = re.compile(r"(https?://[^\s]+)")


async def apply(
    last_message: Message, recent_messages: List[Message], config: Dict[str, int]
) -> Optional[Tuple[str, Iterable[Member], Iterable[Message]]]:
    """Detects total links exceeding the limit sent by a single user."""
    relevant_messages = tuple(
        msg
        for msg in recent_messages
        if msg.author == last_message.author
    )
    total_links = 0
    messages_with_links = 0

    for msg in relevant_messages:
        total_matches = len(LINK_RE.findall(msg.content))
        if total_matches:
            messages_with_links += 1
            total_links += total_matches

    # Only apply the filter if we found more than one message with
    # links to prevent wrongfully firing the rule on users posting
    # e.g. an installation log of pip packages from GitHub.
    if total_links > config['max'] and messages_with_links > 1:
        return (
            f"sent {total_links} links in {config['interval']}s",
            (last_message.author,),
            relevant_messages
        )
    return None
