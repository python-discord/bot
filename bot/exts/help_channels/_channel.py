import logging
import typing as t
from datetime import timedelta
from enum import Enum

import arrow
import discord
from arrow import Arrow

import bot
from bot import constants
from bot.exts.help_channels import _caches, _message
from bot.utils.channel import try_get_channel

log = logging.getLogger(__name__)

MAX_CHANNELS_PER_CATEGORY = 50
EXCLUDED_CHANNELS = (constants.Channels.cooldown,)


class ClosingReason(Enum):
    """All possible closing reasons for help channels."""

    COMMAND = "command"
    LATEST_MESSSAGE = "auto.latest_message"
    CLAIMANT_TIMEOUT = "auto.claimant_timeout"
    OTHER_TIMEOUT = "auto.other_timeout"
    DELETED = "auto.deleted"
    CLEANUP = "auto.cleanup"


def get_category_channels(category: discord.CategoryChannel) -> t.Iterable[discord.TextChannel]:
    """Yield the text channels of the `category` in an unsorted manner."""
    log.trace(f"Getting text channels in the category '{category}' ({category.id}).")

    # This is faster than using category.channels because the latter sorts them.
    for channel in category.guild.channels:
        if channel.category_id == category.id and not is_excluded_channel(channel):
            yield channel


async def get_closing_time(channel: discord.TextChannel, init_done: bool) -> t.Tuple[Arrow, ClosingReason]:
    """
    Return the time at which the given help `channel` should be closed along with the reason.

    `init_done` is True if the cog has finished loading and False otherwise.

    The time is calculated as follows:

    * If `init_done` is True or the cached time for the claimant's last message is unavailable,
      add the configured `idle_minutes_claimant` to the time the most recent message was sent.
    * If the help session is empty (see `is_empty`), do the above but with `deleted_idle_minutes`.
    * If either of the above is attempted but the channel is completely empty, close the channel
      immediately.
    * Otherwise, retrieve the times of the claimant's and non-claimant's last messages from the
      cache. Add the configured `idle_minutes_claimant` and idle_minutes_others`, respectively, and
      choose the time which is furthest in the future.
    """
    log.trace(f"Getting the closing time for #{channel} ({channel.id}).")

    is_empty = await _message.is_empty(channel)
    if is_empty:
        idle_minutes_claimant = constants.HelpChannels.deleted_idle_minutes
    else:
        idle_minutes_claimant = constants.HelpChannels.idle_minutes_claimant

    claimant_time = await _caches.claimant_last_message_times.get(channel.id)

    # The current session lacks messages, the cog is still starting, or the cache is empty.
    if is_empty or not init_done or claimant_time is None:
        msg = await _message.get_last_message(channel)
        if not msg:
            log.debug(f"No idle time available; #{channel} ({channel.id}) has no messages, closing now.")
            return Arrow.min, ClosingReason.DELETED

        # Use the greatest offset to avoid the possibility of prematurely closing the channel.
        time = Arrow.fromdatetime(msg.created_at) + timedelta(minutes=idle_minutes_claimant)
        reason = ClosingReason.DELETED if is_empty else ClosingReason.LATEST_MESSSAGE
        return time, reason

    claimant_time = Arrow.utcfromtimestamp(claimant_time)
    others_time = await _caches.non_claimant_last_message_times.get(channel.id)

    if others_time:
        others_time = Arrow.utcfromtimestamp(others_time)
    else:
        # The help session hasn't received any answers (messages from non-claimants) yet.
        # Set to min value so it isn't considered when calculating the closing time.
        others_time = Arrow.min

    # Offset the cached times by the configured values.
    others_time += timedelta(minutes=constants.HelpChannels.idle_minutes_others)
    claimant_time += timedelta(minutes=idle_minutes_claimant)

    # Use the time which is the furthest into the future.
    if claimant_time >= others_time:
        closing_time = claimant_time
        reason = ClosingReason.CLAIMANT_TIMEOUT
    else:
        closing_time = others_time
        reason = ClosingReason.OTHER_TIMEOUT

    log.trace(f"#{channel} ({channel.id}) should be closed at {closing_time} due to {reason}.")
    return closing_time, reason


async def get_in_use_time(channel_id: int) -> t.Optional[timedelta]:
    """Return the duration `channel_id` has been in use. Return None if it's not in use."""
    log.trace(f"Calculating in use time for channel {channel_id}.")

    claimed_timestamp = await _caches.claim_times.get(channel_id)
    if claimed_timestamp:
        claimed = Arrow.utcfromtimestamp(claimed_timestamp)
        return arrow.utcnow() - claimed


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
