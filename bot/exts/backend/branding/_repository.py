import logging

from bot.bot import Bot

log = logging.getLogger(__name__)


class BrandingRepository:
    """Abstraction exposing the branding repository via convenient methods."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
