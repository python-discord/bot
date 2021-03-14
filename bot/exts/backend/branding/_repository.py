import logging
import typing as t
from datetime import date, datetime

import frontmatter

from bot.bot import Bot
from bot.constants import Keys
from bot.errors import BrandingMisconfiguration

# Base URL for requests into the branding repository
BRANDING_URL = "https://api.github.com/repos/kwzrd/pydis-branding/contents"

PARAMS = {"ref": "kwzrd/events-rework"}  # Target branch
HEADERS = {"Accept": "application/vnd.github.v3+json"}  # Ensure we use API v3

# A GitHub token is not necessary for the cog to operate, unauthorized requests are however limited to 60 per hour
if Keys.github:
    HEADERS["Authorization"] = f"token {Keys.github}"

# Since event periods are year-agnostic, we parse them into `datetime` objects with a manually inserted year
# Please note that this is intentionally a leap year in order to allow Feb 29 to be valid
ARBITRARY_YEAR = 2020

# Format used to parse date strings after we inject `ARBITRARY_YEAR` at the end
DATE_FMT = "%B %d %Y"  # Ex: July 10 2020

log = logging.getLogger(__name__)


class RemoteObject:
    """
    Represent a remote file or directory on GitHub.

    The annotations match keys in the response JSON that we're interested in.
    """

    sha: str  # Hash helps us detect asset change
    name: str  # Filename
    path: str  # Path from repo root
    type: str  # Either 'file' or 'dir'
    download_url: t.Optional[str]  # If type is 'dir', this is None!

    def __init__(self, dictionary: t.Dict[str, t.Any]) -> None:
        """Initialize by grabbing annotated attributes from `dictionary`."""
        for annotation in self.__annotations__:
            setattr(self, annotation, dictionary[annotation])


class MetaFile(t.NamedTuple):
    """Composition of attributes defined in a 'meta.md' file."""

    is_fallback: bool
    start_date: t.Optional[date]
    end_date: t.Optional[date]
    description: str  # Markdown event description


class Event(t.NamedTuple):
    """Represent an event defined in the branding repository."""

    path: str  # Path from repo root where event lives
    meta: MetaFile
    banner: RemoteObject
    icons: t.List[RemoteObject]

    def __str__(self) -> str:
        return f"<Event at '{self.path}'>"


class BrandingRepository:
    """
    Branding repository abstraction.

    This class represents the branding repository's main branch and exposes available events and assets as objects.

    The API is primarily formed by the `get_current_event` function. It performs the necessary amount of validation
    to ensure that a misconfigured event isn't returned. Such events are simply ignored, and will be substituted
    with the fallback event, if available.

    Warning logs will inform core developers if a misconfigured event is encountered.

    Colliding events cause no special behaviour - in such cases, the first found active event is returned.
    We work with the assumption that the branding repository checks for such conflicts and prevents them
    from reaching the main branch.

    This class keeps no internal state. All `get_current_event` calls will result in GitHub API requests.
    The caller is therefore responsible for being responsible and caching information to prevent API abuse.

    Requests are made using the HTTP session looked up on the bot instance.
    """

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

    async def fetch_file(self, download_url: str) -> t.Optional[bytes]:
        """
        Fetch file from `download_url`.

        Returns the file as bytes unless the request fails, in which case None is given.
        """
        log.debug(f"Fetching file from branding repository: {download_url}")

        async with self.bot.http_session.get(download_url, params=PARAMS, headers=HEADERS) as response:
            if response.status == 200:
                return await response.read()
            else:
                log.warning(f"Received non-200 response status: {response.status}")

    async def parse_meta_file(self, raw_file: bytes) -> MetaFile:
        """
        Parse a 'meta.md' file from raw bytes.

        The caller is responsible for handling errors caused by misconfiguration.
        """
        attrs, description = frontmatter.parse(raw_file)  # Library automatically decodes using UTF-8

        if not description:
            raise BrandingMisconfiguration("No description found in 'meta.md'!")

        if attrs.get("fallback", False):
            return MetaFile(is_fallback=True, start_date=None, end_date=None, description=description)

        start_date_raw = attrs.get("start_date")
        end_date_raw = attrs.get("end_date")

        if None in (start_date_raw, end_date_raw):
            raise BrandingMisconfiguration("Non-fallback event doesn't have start and end dates defined!")

        # We extend the configured month & day with an arbitrary leap year to allow a `datetime` repr to exist
        # This may raise errors if configured in a wrong format ~ we let the caller handle such cases
        start_date = datetime.strptime(f"{start_date_raw} {ARBITRARY_YEAR}", DATE_FMT).date()
        end_date = datetime.strptime(f"{end_date_raw} {ARBITRARY_YEAR}", DATE_FMT).date()

        return MetaFile(is_fallback=False, start_date=start_date, end_date=end_date, description=description)

    async def construct_event(self, directory: RemoteObject) -> Event:
        """
        Construct an `Event` instance from an event `directory`.

        The caller is responsible for handling errors caused by misconfiguration.
        """
        contents = await self.fetch_directory(directory.path)

        missing_assets = {"meta.md", "banner.png", "server_icons"} - contents.keys()

        if missing_assets:
            raise BrandingMisconfiguration(f"Directory is missing following assets: {missing_assets}")

        server_icons = await self.fetch_directory(contents["server_icons"].path, types=("file",))

        if server_icons is None:
            raise BrandingMisconfiguration("Failed to fetch server icons!")
        if len(server_icons) == 0:
            raise BrandingMisconfiguration("Found no server icons!")

        meta_bytes = await self.fetch_file(contents["meta.md"].download_url)

        if meta_bytes is None:
            raise BrandingMisconfiguration("Failed to fetch 'meta.md' file!")

        meta_file = await self.parse_meta_file(meta_bytes)

        return Event(directory.path, meta_file, contents["banner.png"], list(server_icons.values()))

    async def get_events(self) -> t.List[Event]:
        """
        Discover available events in the branding repository.

        Misconfigured events are skipped, the return value may therefore not contain a representation of each
        directory in the repository. May return an empty list in the catastrophic case.
        """
        log.debug("Discovering events in branding repository")

        event_directories = await self.fetch_directory("events", types=("dir",))  # Skip files
        instances: t.List[Event] = []

        for event_directory in event_directories.values():
            log.trace(f"Attempting to construct event from directory: {event_directory.path}")
            try:
                instance = await self.construct_event(event_directory)
            except Exception as exc:
                log.warning(f"Could not construct event '{event_directory.path}': {exc}")
            else:
                instances.append(instance)

        log.trace(f"Found {len(instances)} correctly configured events")
        return instances

    async def get_current_event(self) -> t.Tuple[t.Optional[Event], t.List[Event]]:
        """
        Get the currently active event, or the fallback event.

        The second return value is a list of all available events. The caller may discard it, if not needed.
        Returning all events alongside the current one prevents having to query the API twice in some cases.

        The current event may be None in the case that no event is active, and no fallback event is found.
        """
        utc_now = datetime.utcnow()
        log.debug(f"Finding active event for: {utc_now}")

        # As all events exist in the arbitrary year, we construct a separate object for the purposes of comparison
        lookup_now = date(year=ARBITRARY_YEAR, month=utc_now.month, day=utc_now.day)

        available_events = await self.get_events()

        for event in available_events:
            meta = event.meta
            if not meta.is_fallback and (meta.start_date <= lookup_now <= meta.end_date):
                return event, available_events

        log.debug("No active event found, looking for fallback")

        for event in available_events:
            if event.meta.is_fallback:
                return event, available_events

        log.warning("No event is currently active and no fallback event was found!")
        return None, available_events
