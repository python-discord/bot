import logging

from bot.bot import Bot
from bot.constants import Keys

# Base URL for requests into the branding repository
BRANDING_URL = "https://api.github.com/repos/kwzrd/pydis-branding/contents"

PARAMS = {"ref": "kwzrd/events-rework"}  # Target branch
HEADERS = {"Accept": "application/vnd.github.v3+json"}  # Ensure we use API v3

# A GitHub token is not necessary for the cog to operate, unauthorized requests are however limited to 60 per hour
if Keys.github:
    HEADERS["Authorization"] = f"token {Keys.github}"

log = logging.getLogger(__name__)


class BrandingRepository:
    """Abstraction exposing the branding repository via convenient methods."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
