import random
import re
from typing import Dict, Iterable, List, Optional, Tuple

from discord import Embed, Member, Message

from bot.constants import Colours, Guild, NEGATIVE_REPLIES

# Generate regex for checking for pings:
guild_id = Guild.id
EVERYONE_RE_INLINE_CODE = re.compile(rf"^(?!`)@everyone(?!`)$|^(?!`)<@&{guild_id}>(?!`)$")
EVERYONE_RE_MULTILINE_CODE = re.compile(rf"^(?!```)@everyone(?!```)$|^(?!```)<@&{guild_id}>(?!```)$")


async def apply(
    last_message: Message,
    recent_messages: List[Message],
    config: Dict[str, int],
) -> Optional[Tuple[str, Iterable[Member], Iterable[Message]]]:
    """Detects if a user has sent an '@everyone' ping."""
    relevant_messages = tuple(msg for msg in recent_messages if msg.author == last_message.author)

    everyone_messages_count = 0
    for msg in relevant_messages:
        num_everyone_pings_inline = len(re.findall(EVERYONE_RE_INLINE_CODE, msg.content))
        num_everyone_pings_multiline = len(re.findall(EVERYONE_RE_MULTILINE_CODE, msg.content))
        if num_everyone_pings_inline and num_everyone_pings_multiline:
            everyone_messages_count += 1

    if everyone_messages_count > config["max"]:
        # Send the channel an embed giving the user more info:
        embed_text = f"Please don't try to ping {last_message.guild.member_count:,} people."
        embed = Embed(title=random.choice(NEGATIVE_REPLIES), description=embed_text, colour=Colours.soft_red)
        await last_message.channel.send(embed=embed)

        return (
            "pinged the everyone role",
            (last_message.author,),
            relevant_messages,
        )
    return None
