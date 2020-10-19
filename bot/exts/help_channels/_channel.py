import logging
import typing as t
from datetime import datetime, timedelta

import discord
from async_rediscache import RedisCache

from bot import constants
from bot.exts.help_channels import _message

log = logging.getLogger(__name__)

MAX_CHANNELS_PER_CATEGORY = 50
EXCLUDED_CHANNELS = (constants.Channels.how_to_get_help, constants.Channels.cooldown)

# This dictionary maps a help channel to the time it was claimed
# RedisCache[discord.TextChannel.id, UtcPosixTimestamp]
_claim_times = RedisCache(namespace="HelpChannels.claim_times")


def get_category_channels(category: discord.CategoryChannel) -> t.Iterable[discord.TextChannel]:
    """Yield the text channels of the `category` in an unsorted manner."""
    log.trace(f"Getting text channels in the category '{category}' ({category.id}).")

    # This is faster than using category.channels because the latter sorts them.
    for channel in category.guild.channels:
        if channel.category_id == category.id and not is_excluded_channel(channel):
            yield channel


async def get_idle_time(channel: discord.TextChannel) -> t.Optional[int]:
    """
    Return the time elapsed, in seconds, since the last message sent in the `channel`.

    Return None if the channel has no messages.
    """
    log.trace(f"Getting the idle time for #{channel} ({channel.id}).")

    msg = await _message.get_last_message(channel)
    if not msg:
        log.debug(f"No idle time available; #{channel} ({channel.id}) has no messages.")
        return None

    idle_time = (datetime.utcnow() - msg.created_at).seconds

    log.trace(f"#{channel} ({channel.id}) has been idle for {idle_time} seconds.")
    return idle_time


async def get_in_use_time(channel_id: int) -> t.Optional[timedelta]:
    """Return the duration `channel_id` has been in use. Return None if it's not in use."""
    log.trace(f"Calculating in use time for channel {channel_id}.")

    claimed_timestamp = await _claim_times.get(channel_id)
    if claimed_timestamp:
        claimed = datetime.utcfromtimestamp(claimed_timestamp)
        return datetime.utcnow() - claimed


def is_excluded_channel(channel: discord.abc.GuildChannel) -> bool:
    """Check if a channel should be excluded from the help channel system."""
    return not isinstance(channel, discord.TextChannel) or channel.id in EXCLUDED_CHANNELS
