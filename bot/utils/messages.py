import asyncio
import contextlib
from io import BytesIO
from typing import Optional, Sequence, Union

from discord import Client, Embed, File, Member, Message, Reaction, TextChannel, Webhook
from discord.abc import Snowflake
from discord.errors import HTTPException

from bot.constants import Emojis

MAX_SIZE = 1024 * 1024 * 8  # 8 Mebibytes


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
            reaction.message.id == message.id
            and str(reaction.emoji) in deletion_emojis
            and user.id in user_ids
        )

    with contextlib.suppress(asyncio.TimeoutError):
        await bot.wait_for('reaction_add', check=check, timeout=timeout)
        await message.delete()


async def send_attachments(message: Message, destination: Union[TextChannel, Webhook]) -> None:
    """
    Re-uploads each attachment in a message to the given channel or webhook.

    Each attachment is sent as a separate message to more easily comply with the 8 MiB request size limit.
    If attachments are too large, they are instead grouped into a single embed which links to them.
    """
    large = []
    for attachment in message.attachments:
        try:
            # This should avoid most files that are too large, but some may get through hence the try-catch.
            # Allow 512 bytes of leeway for the rest of the request.
            if attachment.size <= MAX_SIZE - 512:
                with BytesIO() as file:
                    await attachment.save(file)
                    attachment_file = File(file, filename=attachment.filename)

                    if isinstance(destination, TextChannel):
                        await destination.send(file=attachment_file)
                    else:
                        await destination.send(
                            file=attachment_file,
                            username=message.author.display_name,
                            avatar_url=message.author.avatar_url
                        )
            else:
                large.append(attachment)
        except HTTPException as e:
            if e.status == 413:
                large.append(attachment)
            else:
                raise

    if large:
        embed = Embed(description=f"\n".join(f"[{attachment.filename}]({attachment.url})" for attachment in large))
        embed.set_footer(text="Attachments exceed upload size limit.")
        if isinstance(destination, TextChannel):
            await destination.send(embed=embed)
        else:
            await destination.send(
                embed=embed,
                username=message.author.display_name,
                avatar_url=message.author.avatar_url
            )
