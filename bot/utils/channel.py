import logging

import discord

import bot
from bot import constants
from bot.constants import Categories

log = logging.getLogger(__name__)


def is_help_channel(channel: discord.TextChannel) -> bool:
    """Return True if `channel` is in one of the help categories (excluding dormant)."""
    log.trace(f"Checking if #{channel} is a help channel.")
    categories = (Categories.help_available, Categories.help_in_use)

    return any(is_in_category(channel, category) for category in categories)


def is_mod_channel(channel: discord.TextChannel) -> bool:
    """True if `channel` is considered a mod channel."""
    if channel.id in constants.MODERATION_CHANNELS:
        log.trace(f"Channel #{channel} is a configured mod channel")
        return True

    elif any(is_in_category(channel, category) for category in constants.MODERATION_CATEGORIES):
        log.trace(f"Channel #{channel} is in a configured mod category")
        return True

    else:
        log.trace(f"Channel #{channel} is not a mod channel")
        return False


def is_staff_channel(channel: discord.TextChannel) -> bool:
    """True if `channel` is considered a staff channel."""
    guild = bot.instance.get_guild(constants.Guild.id)

    if channel.type is discord.ChannelType.category:
        return False

    # Channel is staff-only if staff have explicit read allow perms
    # and @everyone has explicit read deny perms
    return any(
        channel.overwrites_for(guild.get_role(staff_role)).read_messages is True
        and channel.overwrites_for(guild.default_role).read_messages is False
        for staff_role in constants.STAFF_ROLES
    )


def is_in_category(channel: discord.TextChannel, category_id: int) -> bool:
    """Return True if `channel` is within a category with `category_id`."""
    return getattr(channel, "category_id", None) == category_id


async def try_get_channel(channel_id: int) -> discord.abc.GuildChannel:
    """Attempt to get or fetch a channel and return it."""
    log.trace(f"Getting the channel {channel_id}.")

    channel = bot.instance.get_channel(channel_id)
    if not channel:
        log.debug(f"Channel {channel_id} is not in cache; fetching from API.")
        channel = await bot.instance.fetch_channel(channel_id)

    log.trace(f"Channel #{channel} ({channel_id}) retrieved.")
    return channel
