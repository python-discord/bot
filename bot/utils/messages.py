import asyncio
import contextlib
import logging
from io import BytesIO
from typing import List, Optional, Sequence, Union

from discord import Client, Embed, File, Member, Message, Reaction, TextChannel, Webhook
from discord.abc import Snowflake
from discord.errors import HTTPException

from bot.constants import Emojis

log = logging.getLogger(__name__)


async def wait_for_deletion(
    message: Message,
    user_ids: Sequence[Snowflake],
    deletion_emojis: Sequence[str] = (Emojis.trashcan,),
    timeout: float = 60 * 5,
    attach_emojis: bool = True,
    client: Optional[Client] = None
) -> None:
    """
    Wait for up to `timeout` seconds for a reaction by any of the specified `user_ids` to delete the message.

    An `attach_emojis` bool may be specified to determine whether to attach the given
    `deletion_emojis` to the message in the given `context`

    A `client` instance may be optionally specified, otherwise client will be taken from the
    guild of the message.
    """
    if message.guild is None and client is None:
        raise ValueError("Message must be sent on a guild")

    bot = client or message.guild.me

    if attach_emojis:
        for emoji in deletion_emojis:
            await message.add_reaction(emoji)

    def check(reaction: Reaction, user: Member) -> bool:
        """Check that the deletion emoji is reacted by the appropriate user."""
        return (
            reaction.message.id == message.id and
            str(reaction.emoji) in deletion_emojis and
            user.id in user_ids
        )

    with contextlib.suppress(asyncio.TimeoutError):
        await bot.wait_for('reaction_add', check=check, timeout=timeout)
        await message.delete()


async def send_attachments(
    message: Message,
    destination: Union[TextChannel, Webhook],
    link_large: bool = True
) -> List[str]:
    """
    Re-upload the message's attachments to the destination and return a list of their new URLs.

    Each attachment is sent as a separate message to more easily comply with the request/file size
    limit. If link_large is True, attachments which are too large are instead grouped into a single
    embed which links to them.
    """
    large = []
    urls = []
    for attachment in message.attachments:
        failure_msg = (
            f"Failed to re-upload attachment {attachment.filename} from message {message.id}"
        )

        try:
            # Allow 512 bytes of leeway for the rest of the request.
            # This should avoid most files that are too large,
            # but some may get through hence the try-catch.
            if attachment.size <= destination.guild.filesize_limit - 512:
                with BytesIO() as file:
                    await attachment.save(file, use_cached=True)
                    attachment_file = File(file, filename=attachment.filename)

                    if isinstance(destination, TextChannel):
                        msg = await destination.send(file=attachment_file)
                        urls.append(msg.attachments[0].url)
                    else:
                        await destination.send(
                            file=attachment_file,
                            username=message.author.display_name,
                            avatar_url=message.author.avatar_url
                        )
            elif link_large:
                large.append(attachment)
            else:
                log.warning(f"{failure_msg} because it's too large.")
        except HTTPException as e:
            if link_large and e.status == 413:
                large.append(attachment)
            else:
                log.warning(f"{failure_msg} with status {e.status}.")

    if link_large and large:
        desc = f"\n".join(f"[{attachment.filename}]({attachment.url})" for attachment in large)
        embed = Embed(description=desc)
        embed.set_footer(text="Attachments exceed upload size limit.")

        if isinstance(destination, TextChannel):
            await destination.send(embed=embed)
        else:
            await destination.send(
                embed=embed,
                username=message.author.display_name,
                avatar_url=message.author.avatar_url
            )

    return urls
