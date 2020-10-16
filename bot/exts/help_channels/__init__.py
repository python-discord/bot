import logging

from bot import constants
from bot.bot import Bot
from bot.exts.help_channels._channel import MAX_CHANNELS_PER_CATEGORY

log = logging.getLogger(__name__)


def validate_config() -> None:
    """Raise a ValueError if the cog's config is invalid."""
    log.trace("Validating config.")
    total = constants.HelpChannels.max_total_channels
    available = constants.HelpChannels.max_available

    if total == 0 or available == 0:
        raise ValueError("max_total_channels and max_available and must be greater than 0.")

    if total < available:
        raise ValueError(
            f"max_total_channels ({total}) must be greater than or equal to max_available "
            f"({available})."
        )

    if total > MAX_CHANNELS_PER_CATEGORY:
        raise ValueError(
            f"max_total_channels ({total}) must be less than or equal to "
            f"{MAX_CHANNELS_PER_CATEGORY} due to Discord's limit on channels per category."
        )


def setup(bot: Bot) -> None:
    """Load the HelpChannels cog."""
    # Defer import to reduce side effects from importing the help_channels package.
    from bot.exts.help_channels._cog import HelpChannels
    try:
        validate_config()
    except ValueError as e:
        log.error(f"HelpChannels cog will not be loaded due to misconfiguration: {e}")
    else:
        bot.add_cog(HelpChannels(bot))
