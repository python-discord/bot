import asyncio
import contextlib
from io import BytesIO
from typing import Sequence

from discord import Embed, File, Message, TextChannel
from discord.abc import Snowflake
from discord.errors import HTTPException

MAX_SIZE = 1024 * 1024 * 8  # 8 Mebibytes


async def wait_for_deletion(
    message: Message,
    user_ids: Sequence[Snowflake],
    deletion_emojis: Sequence[str]=("❌",),
    timeout: float=60 * 5,
    attach_emojis=True,
    client=None
):
    """
    Waits for up to `timeout` seconds for a reaction by
    any of the specified `user_ids` to delete the message.

    Args:
        message (Message):
            The message that should be monitored for reactions
            and possibly deleted. Must be a message sent on a
            guild since access to the bot instance is required.

        user_ids (Sequence[Snowflake]):
            A sequence of users that are allowed to delete
            this message.

    Kwargs:
        deletion_emojis (Sequence[str]):
            A sequence of emojis that are considered deletion
            emojis.

        timeout (float):
            A positive float denoting the maximum amount of
            time to wait for a deletion reaction.

        attach_emojis (bool):
            Whether to attach the given `deletion_emojis`
            to the message in the given `context`

        client (Optional[discord.Client]):
            The client instance handling the original command.
            If not given, will take the client from the guild
            of the message.
    """

    if message.guild is None and client is None:
        raise ValueError("Message must be sent on a guild")

    bot = client or message.guild.me

    if attach_emojis:
        for emoji in deletion_emojis:
            await message.add_reaction(emoji)

    def check(reaction, user):
        return (
            reaction.message.id == message.id and
            reaction.emoji in deletion_emojis and
            user.id in user_ids
        )

    with contextlib.suppress(asyncio.TimeoutError):
        await bot.wait_for(
            'reaction_add',
            check=check,
            timeout=timeout
        )
        await message.delete()


async def send_attachments(message: Message, destination: TextChannel):
    """
    Re-uploads each attachment in a message to the given channel.

    Each attachment is sent as a separate message to more easily comply with the 8 MiB request size limit.
    If attachments are too large, they are instead grouped into a single embed which links to them.

    :param message: the message whose attachments to re-upload
    :param destination: the channel in which to re-upload the attachments
    """

    large = []
    for attachment in message.attachments:
        try:
            # This should avoid most files that are too large, but some may get through hence the try-catch.
            # Allow 512 bytes of leeway for the rest of the request.
            if attachment.size <= MAX_SIZE - 512:
                with BytesIO() as file:
                    await attachment.save(file)
                    await destination.send(file=File(file, filename=attachment.filename))
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
        await destination.send(embed=embed)
