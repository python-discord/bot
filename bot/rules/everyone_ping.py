import random
from typing import Dict, Iterable, List, Optional, Tuple

from discord import Embed, Member, Message

from bot.constants import Colours, NEGATIVE_REPLIES


async def apply(
    last_message: Message,
    recent_messages: List[Message],
    config: Dict[str, int],
) -> Optional[Tuple[str, Iterable[Member], Iterable[Message]]]:
    """Detects if a user has sent an '@everyone' ping."""
    relevant_messages = tuple(msg for msg in recent_messages if msg.author == last_message.author)

    everyone_messages_count = 0
    for msg in relevant_messages:
        if "@everyone" in msg.content:
            everyone_messages_count += 1

    if everyone_messages_count > config["max"]:
        # Send the user an embed giving them more info:
        embed_text = f"Please don't try to ping {last_message.guild.member_count:,} people."

        # Make embed:
        embed = Embed(title=random.choice(NEGATIVE_REPLIES), description=embed_text, colour=Colours.soft_red)

        # Send embed:
        await last_message.channel.send(embed=embed)
        return (
            f"pinged the everyone role {everyone_messages_count} times in {config['interval']}s",
            (last_message.author,),
            relevant_messages,
        )
    return None
