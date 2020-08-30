import textwrap
from typing import Dict, Iterable, List, Optional, Tuple

from discord import Embed, Member, Message

from bot.constants import Colours


async def apply(
    last_message: Message,
    recent_messages: List[Message],
    config: Dict[str, int],
) -> Optional[Tuple[str, Iterable[Member], Iterable[Message]]]:
    """Detects if a user has sent an '@everyone' ping."""
    relevant_messages = tuple(msg for msg in recent_messages if msg.author == last_message.author)

    ev_msgs_ct = 0
    for msg in relevant_messages:
        if "@everyone" in msg.content:
            ev_msgs_ct += 1

    if ev_msgs_ct > config["max"]:
        # Send the user an embed giving them more info:
        embed_text = textwrap.dedent(
            f"""
            Please don't try to ping {last_message.guild.member_count:,} people.
            **It will not have good results.**
        """
        )
        embed = Embed(description=embed_text, colour=Colours.soft_red)
        await last_message.channel.send(f"Hey {last_message.author.mention}!", embed=embed)
        return (
            f"pinged the everyone role {ev_msgs_ct} times in {config['interval']}s",
            (last_message.author,),
            relevant_messages,
        )
    return None
