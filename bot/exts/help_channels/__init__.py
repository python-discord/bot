import logging

from bot.bot import Bot

log = logging.getLogger(__name__)


def setup(bot: Bot) -> None:
    """Load the HelpChannels cog."""
    # Defer import to reduce side effects from importing the sync package.
    from bot.exts.help_channels import _cog
    try:
        _cog.validate_config()
    except ValueError as e:
        log.error(f"HelpChannels cog will not be loaded due to misconfiguration: {e}")
    else:
        bot.add_cog(_cog.HelpChannels(bot))
