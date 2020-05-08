import logging

import discord

from bot.constants import Categories

log = logging.getLogger(__name__)


def is_help_channel(channel: discord.TextChannel) -> bool:
    """Return True if `channel` is in one of the help categories (excluding dormant)."""
    log.trace(f"Checking if #{channel} is a help channel.")
    categories = (Categories.help_available, Categories.help_in_use)

    return any(is_in_category(channel, category) for category in categories)


def is_in_category(channel: discord.TextChannel, category_id: int) -> bool:
    """Return True if `channel` is within a category with `category_id`."""
    actual_category = getattr(channel, "category", None)
    return actual_category is not None and actual_category.id == category_id


async def try_get_channel(channel_id: int, client: discord.Client) -> discord.abc.GuildChannel:
    """Attempt to get or fetch a channel and return it."""
    log.trace(f"Getting the channel {channel_id}.")

    channel = client.get_channel(channel_id)
    if not channel:
        log.debug(f"Channel {channel_id} is not in cache; fetching from API.")
        channel = await client.fetch_channel(channel_id)

    log.trace(f"Channel #{channel} ({channel_id}) retrieved.")
    return channel
