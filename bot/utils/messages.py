import asyncio
import contextlib
from typing import Sequence

from discord import Message
from discord.abc import Snowflake


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
