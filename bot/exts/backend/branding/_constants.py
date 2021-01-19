from enum import Enum, IntEnum

from bot.constants import Keys


class Month(IntEnum):
    """All month constants for seasons."""

    JANUARY = 1
    FEBRUARY = 2
    MARCH = 3
    APRIL = 4
    MAY = 5
    JUNE = 6
    JULY = 7
    AUGUST = 8
    SEPTEMBER = 9
    OCTOBER = 10
    NOVEMBER = 11
    DECEMBER = 12

    def __str__(self) -> str:
        return self.name.title()


class AssetType(Enum):
    """
    Discord media assets.

    The values match exactly the kwarg keys that can be passed to `Guild.edit`.
    """

    BANNER = "banner"
    SERVER_ICON = "icon"


STATUS_OK = 200  # HTTP status code

FILE_BANNER = "banner.png"
FILE_AVATAR = "avatar.png"
SERVER_ICONS = "server_icons"

BRANDING_URL = "https://api.github.com/repos/python-discord/branding/contents"

PARAMS = {"ref": "master"}  # Target branch
HEADERS = {"Accept": "application/vnd.github.v3+json"}  # Ensure we use API v3

# A GitHub token is not necessary for the cog to operate,
# unauthorized requests are however limited to 60 per hour
if Keys.github:
    HEADERS["Authorization"] = f"token {Keys.github}"
