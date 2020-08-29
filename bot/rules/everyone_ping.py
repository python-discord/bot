import logging
import textwrap
from typing import Dict, Iterable, List, Optional, Tuple

from discord import Embed, Member, Message

from bot.cogs.moderation.utils import send_private_embed
from bot.constants import Colours

# For embed sender
log = logging.getLogger(__name__)


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
    for msg in relevant_messages:
        if "@everyone" in msg.content:
            ev_msgs_ct += 1

    if ev_msgs_ct > config["max"]:
        # Send the user an embed giving them more info:
        member_count = "{:,}".format(last_message.guild.member_count).split(
            ","
        )[0]
        embed_text = textwrap.dedent(
            f"""
            Hello {last_message.author.display_name}, please don't try to ping {member_count}k people.
            **It will not have good results.**
            If you want to know what it would be like, imagine pinging Greenland. Please don't ping Greenland.
        """
        )
        print(embed_text)
        embed = Embed(
            title="Everyone Ping Mute Info",
            colour=Colours.soft_red,
            description=embed_text,
        )
        await send_private_embed(last_message.author, embed)
        return (
            f"pinged the everyone role {ev_msgs_ct} times in {config['interval']}s",
            (last_message.author,),
            relevant_messages,
        )
    return None
