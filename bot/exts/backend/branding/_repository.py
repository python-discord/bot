import logging
import typing as t

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


class RemoteObject:
    """
    Represent a remote file or directory on GitHub.

    The annotations match keys in the response JSON that we're interested in.
    """

    name: str  # Filename
    path: str  # Path from repo root
    type: str  # Either 'file' or 'dir'
    download_url: str

    def __init__(self, dictionary: t.Dict[str, t.Any]) -> None:
        """Initialize by grabbing annotated attributes from `dictionary`."""
        for annotation in self.__annotations__:
            setattr(self, annotation, dictionary[annotation])


class BrandingRepository:
    """Abstraction exposing the branding repository via convenient methods."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def fetch_directory(self, path: str, types: t.Container[str] = ("file", "dir")) -> t.Dict[str, RemoteObject]:
        """
        Fetch directory found at `path` in the branding repository.

        The directory will be represented by a mapping from file or sub-directory names to their corresponding
        instances of `RemoteObject`. Passing a custom `types` value allows only getting files or directories.

        If the request fails, returns an empty dictionary.
        """
        full_url = f"{BRANDING_URL}/{path}"
        log.debug(f"Fetching directory from branding repository: {full_url}")

        async with self.bot.http_session.get(full_url, params=PARAMS, headers=HEADERS) as response:
            if response.status == 200:
                json_directory = await response.json()
            else:
                log.warning(f"Received non-200 response status: {response.status}")
                return {}

        return {file["name"]: RemoteObject(file) for file in json_directory if file["type"] in types}

    async def fetch_file(self, file: RemoteObject) -> t.Optional[bytes]:
        """
        Fetch `file` using its download URL.

        Returns the file as bytes unless the request fails, in which case None is given.
        """
        log.debug(f"Fetching file from branding repository: {file.download_url}")

        async with self.bot.http_session.get(file.download_url, params=PARAMS, headers=HEADERS) as response:
            if response.status == 200:
                return await response.read()
            else:
                log.warning(f"Received non-200 response status: {response.status}")
