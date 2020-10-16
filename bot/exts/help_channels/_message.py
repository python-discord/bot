import logging

import discord
from async_rediscache import RedisCache

import bot

log = logging.getLogger(__name__)

# This cache maps a help channel to original question message in same channel.
# RedisCache[discord.TextChannel.id, discord.Message.id]
_question_messages = RedisCache(namespace="HelpChannels.question_messages")


async def pin(message: discord.Message) -> None:
    """Pin an initial question `message` and store it in a cache."""
    if await _pin_wrapper(message.id, message.channel, pin=True):
        await _question_messages.set(message.channel.id, message.id)


async def unpin(channel: discord.TextChannel) -> None:
    """Unpin the initial question message sent in `channel`."""
    msg_id = await _question_messages.pop(channel.id)
    if msg_id is None:
        log.debug(f"#{channel} ({channel.id}) doesn't have a message pinned.")
    else:
        await _pin_wrapper(msg_id, channel, pin=False)


async def _pin_wrapper(msg_id: int, channel: discord.TextChannel, *, pin: bool) -> bool:
    """
    Pin message `msg_id` in `channel` if `pin` is True or unpin if it's False.

    Return True if successful and False otherwise.
    """
    channel_str = f"#{channel} ({channel.id})"
    if pin:
        func = bot.instance.http.pin_message
        verb = "pin"
    else:
        func = bot.instance.http.unpin_message
        verb = "unpin"

    try:
        await func(channel.id, msg_id)
    except discord.HTTPException as e:
        if e.code == 10008:
            log.debug(f"Message {msg_id} in {channel_str} doesn't exist; can't {verb}.")
        else:
            log.exception(
                f"Error {verb}ning message {msg_id} in {channel_str}: {e.status} ({e.code})"
            )
        return False
    else:
        log.trace(f"{verb.capitalize()}ned message {msg_id} in {channel_str}.")
        return True
