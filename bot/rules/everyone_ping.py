import random
import re
from typing import Dict, Iterable, List, Optional, Tuple

from discord import Embed, Member, Message

from bot.constants import Colours, Guild, NEGATIVE_REPLIES

# Generate regex for checking for pings:
guild_id = Guild.id
EVERYONE_RE = re.compile(rf".*@everyone.*|.*<@&{guild_id}>.*")
CODEBLOCK_RE = re.compile(
    r"(?P<delim>(?P<block>```)|``?)"        # code delimiter: 1-3 backticks; (?P=block) only matches if it's a block
    r"(?(block)(?:(?P<lang>[a-z]+)\n)?)"    # if we're in a block, match optional language (only letters plus newline)
    r"(?:[ \t]*\n)*"                        # any blank (empty or tabs/spaces only) lines before the code
    r"(?P<code>.*?)"                        # extract all code inside the markup
    r"\s*"                                  # any more whitespace before the end of the code markup
    r"(?P=delim)",                          # match the exact same delimiter from the start again
    re.DOTALL | re.IGNORECASE               # "." also matches newlines, case insensitive
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
        # Remove codeblocks:
        msg_no_codeblocks = re.sub(CODEBLOCK_RE, '', msg.content)

        # Check de-codeblocked message:
        num_everyone_pings = len(re.findall(EVERYONE_RE, msg_no_codeblocks))
        if num_everyone_pings:
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
