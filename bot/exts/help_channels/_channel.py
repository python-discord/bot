import logging
import typing as t
from datetime import datetime, timedelta

import discord

import bot
from bot import constants
from bot.exts.help_channels import _caches, _message
from bot.utils.channel import try_get_channel

log = logging.getLogger(__name__)

MAX_CHANNELS_PER_CATEGORY = 50
EXCLUDED_CHANNELS = (constants.Channels.cooldown,)


def get_category_channels(category: discord.CategoryChannel) -> t.Iterable[discord.TextChannel]:
    """Yield the text channels of the `category` in an unsorted manner."""
    log.trace(f"Getting text channels in the category '{category}' ({category.id}).")

    # This is faster than using category.channels because the latter sorts them.
    for channel in category.guild.channels:
        if channel.category_id == category.id and not is_excluded_channel(channel):
            yield channel


async def get_closing_time(channel: discord.TextChannel) -> t.Optional[int]:
    """Return the timestamp at which the given help `channel` should be closed."""
    log.trace(f"Getting the closing time for #{channel} ({channel.id}).")

    if await _message.is_empty(channel):
        idle_minutes = constants.HelpChannels.deleted_idle_minutes
    else:
        idle_minutes = constants.HelpChannels.idle_minutes_others

    last_message = await _caches.last_message.get(channel.id)
    claimant_last_message = await _caches.claimant_last_message.get(channel.id)

    if not (last_message or claimant_last_message):
        # Using the old method if we can't get cached info.
        msg = await _message.get_last_message(channel)
        if not msg:
            log.debug(f"No idle time available; #{channel} ({channel.id}) has no messages.")
            return datetime.min

        # We want to get the time at which a channel should be closed.
        closing_time = msg.created_at
        closing_time += timedelta(minutes=idle_minutes)

        return closing_time

    # We want to get the time at which a channel should be closed.
    last_message = datetime.fromtimestamp(last_message)
    claimant = datetime.fromtimestamp(claimant_last_message)

    last_message += timedelta(minutes=idle_minutes)
    claimant += timedelta(minutes=constants.HelpChannels.idle_minutes_claimant)

    # The further away closing time is what we should use.
    closing_time = max(claimant, last_message)
    log.trace(f"claimant closing time: {claimant}, last_message closing time: {last_message}")
    log.trace(f"#{channel} ({channel.id}) should be closed at {closing_time}.")
    return closing_time


async def get_in_use_time(channel_id: int) -> t.Optional[timedelta]:
    """Return the duration `channel_id` has been in use. Return None if it's not in use."""
    log.trace(f"Calculating in use time for channel {channel_id}.")

    claimed_timestamp = await _caches.claim_times.get(channel_id)
    if claimed_timestamp:
        claimed = datetime.utcfromtimestamp(claimed_timestamp)
        return datetime.utcnow() - claimed


def is_excluded_channel(channel: discord.abc.GuildChannel) -> bool:
    """Check if a channel should be excluded from the help channel system."""
    return not isinstance(channel, discord.TextChannel) or channel.id in EXCLUDED_CHANNELS


async def move_to_bottom(channel: discord.TextChannel, category_id: int, **options) -> None:
    """
    Move the `channel` to the bottom position of `category` and edit channel attributes.

    To ensure "stable sorting", we use the `bulk_channel_update` endpoint and provide the current
    positions of the other channels in the category as-is. This should make sure that the channel
    really ends up at the bottom of the category.

    If `options` are provided, the channel will be edited after the move is completed. This is the
    same order of operations that `discord.TextChannel.edit` uses. For information on available
    options, see the documentation on `discord.TextChannel.edit`. While possible, position-related
    options should be avoided, as it may interfere with the category move we perform.
    """
    # Get a fresh copy of the category from the bot to avoid the cache mismatch issue we had.
    category = await try_get_channel(category_id)

    payload = [{"id": c.id, "position": c.position} for c in category.channels]

    # Calculate the bottom position based on the current highest position in the category. If the
    # category is currently empty, we simply use the current position of the channel to avoid making
    # unnecessary changes to positions in the guild.
    bottom_position = payload[-1]["position"] + 1 if payload else channel.position

    payload.append(
        {
            "id": channel.id,
            "position": bottom_position,
            "parent_id": category.id,
            "lock_permissions": True,
        }
    )

    # We use d.py's method to ensure our request is processed by d.py's rate limit manager
    await bot.instance.http.bulk_channel_update(category.guild.id, payload)

    # Now that the channel is moved, we can edit the other attributes
    if options:
        await channel.edit(**options)
