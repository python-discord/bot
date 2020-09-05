import random
import re
from typing import Dict, Iterable, List, Optional, Tuple

from discord import Embed, Member, Message

from bot.constants import Colours, Guild, NEGATIVE_REPLIES

# Generate regex for checking for pings:
guild_id = Guild.id
EVERYONE_PING_RE = re.compile(rf"@everyone|<@&{guild_id}>")
CODE_BLOCK_RE = re.compile(
    r"(?P<delim>``?)[^`]+?(?P=delim)(?!`+)"  # Inline codeblock
    r"|```(.+?)```",  # Multiline codeblock
    re.DOTALL | re.MULTILINE
)


async def apply(
    last_message: Message,
    recent_messages: List[Message],
    config: Dict[str, int],
) -> Optional[Tuple[str, Iterable[Member], Iterable[Message]]]:
    """Detects if a user has sent an '@everyone' ping."""
    relevant_messages = tuple(msg for msg in recent_messages if msg.author == last_message.author)

    everyone_messages_count = 0
    for msg in relevant_messages:
        content = CODE_BLOCK_RE.sub("", msg.content)  # Remove codeblocks in the message
        if matches := len(EVERYONE_PING_RE.findall(content)):
            everyone_messages_count += matches

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
