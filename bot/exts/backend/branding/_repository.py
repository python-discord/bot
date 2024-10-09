import typing as t
from datetime import UTC, date, datetime

import frontmatter
from aiohttp import ClientResponse, ClientResponseError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from bot.bot import Bot
from bot.constants import Keys
from bot.errors import BrandingMisconfigurationError
from bot.log import get_logger

# Base URL for requests into the branding repository.
BRANDING_URL = "https://api.github.com/repos/python-discord/branding/contents"

PARAMS = {"ref": "main"}  # Target branch.
HEADERS = {"Accept": "application/vnd.github.v3+json"}  # Ensure we use API v3.

# A GitHub token is not necessary. However, unauthorized requests are limited to 60 per hour.
if Keys.github:
    HEADERS["Authorization"] = f"token {Keys.github}"

# Since event periods are year-agnostic, we parse them into `datetime` objects with a manually inserted year.
# Please note that this is intentionally a leap year to allow Feb 29 to be valid.
ARBITRARY_YEAR = 2020

# Format used to parse date strings after we inject `ARBITRARY_YEAR` at the end.
DATE_FMT = "%B %d %Y"  # Ex: July 10 2020

log = get_logger(__name__)


class RemoteObject:
    """
    Remote file or directory on GitHub.

    The annotations match keys in the response JSON that we're interested in.
    """

    sha: str  # Hash helps us detect asset change.
    name: str  # Filename.
    path: str  # Path from repo root.
    type: str  # Either 'file' or 'dir'.
    download_url: str | None  # If type is 'dir', this is None!

    def __init__(self, dictionary: dict[str, t.Any]) -> None:
        """Initialize by grabbing annotated attributes from `dictionary`."""
        missing_keys = self.__annotations__.keys() - dictionary.keys()
        if missing_keys:
            raise KeyError(f"Fetched object lacks expected keys: {missing_keys}")
        for annotation in self.__annotations__:
            setattr(self, annotation, dictionary[annotation])


class MetaFile(t.NamedTuple):
    """Attributes defined in a 'meta.md' file."""

    is_fallback: bool
    start_date: date | None
    end_date: date | None
    description: str  # Markdown event description.


class Event(t.NamedTuple):
    """Event defined in the branding repository."""

    path: str  # Path from repo root where event lives. This is the event's identity.
    meta: MetaFile
    banners: list[RemoteObject]
    icons: list[RemoteObject]

    def __str__(self) -> str:
        return f"<Event at '{self.path}'>"


class GitHubServerError(Exception):
    """
    GitHub responded with 5xx status code.

    Such error shall be retried.
    """


def _raise_for_status(resp: ClientResponse) -> None:
    """Raise custom error if resp status is 5xx."""
    # Use the response's raise_for_status so that we can
    # attach the full traceback to our custom error.
    log.trace(f"GitHub response status: {resp.status}")
    try:
        resp.raise_for_status()
    except ClientResponseError as err:
        if resp.status >= 500:
            raise GitHubServerError from err
        raise


_retry_fetch = retry(
    retry=retry_if_exception_type(GitHubServerError),  # Only retry this error.
    stop=stop_after_attempt(5),  # Up to 5 attempts.
    wait=wait_exponential(),  # Exponential backoff: 1, 2, 4, 8 seconds.
    reraise=True,  # After final failure, re-raise original exception.
)


class BrandingRepository:
    """
    Branding repository abstraction.

    This class represents the branding repository's main branch and exposes available events and assets
    as objects. It performs the necessary amount of validation to ensure that a misconfigured event
    isn't returned. Such events are simply ignored, and will be substituted with the fallback event,
    if available. Warning logs will inform core developers if a misconfigured event is encountered.

    Colliding events cause no special behaviour. In such cases, the first found active event is returned.
    We work with the assumption that the branding repository checks for such conflicts and prevents them
    from reaching the main branch.

    This class keeps no internal state. All `get_current_event` calls will result in GitHub API requests.
    The caller is therefore responsible for being responsible and caching information to prevent API abuse.

    Requests are made using the HTTP session looked up on the bot instance.
    """

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @_retry_fetch
    async def fetch_directory(self, path: str, types: t.Container[str] = ("file", "dir")) -> dict[str, RemoteObject]:
        """
        Fetch directory found at `path` in the branding repository.

        Raise an exception if the request fails, or if the response lacks the expected keys.

        Passing custom `types` allows getting only files or directories. By default, both are included.
        """
        full_url = f"{BRANDING_URL}/{path}"
        log.debug(f"Fetching directory from branding repository: '{full_url}'.")

        async with self.bot.http_session.get(full_url, params=PARAMS, headers=HEADERS) as response:
            _raise_for_status(response)
            json_directory = await response.json()

        return {file["name"]: RemoteObject(file) for file in json_directory if file["type"] in types}

    @_retry_fetch
    async def fetch_file(self, download_url: str) -> bytes:
        """
        Fetch file as bytes from `download_url`.

        Raise an exception if the request does not succeed.
        """
        log.debug(f"Fetching file from branding repository: '{download_url}'.")

        async with self.bot.http_session.get(download_url, params=PARAMS, headers=HEADERS) as response:
            _raise_for_status(response)
            return await response.read()

    def parse_meta_file(self, raw_file: bytes) -> MetaFile:
        """
        Parse a 'meta.md' file from raw bytes.

        The caller is responsible for handling errors caused by misconfiguration.
        """
        attrs, description = frontmatter.parse(raw_file, encoding="UTF-8")

        if not description:
            raise BrandingMisconfigurationError("No description found in 'meta.md'!")

        if attrs.get("fallback", False):
            return MetaFile(is_fallback=True, start_date=None, end_date=None, description=description)

        start_date_raw = attrs.get("start_date")
        end_date_raw = attrs.get("end_date")

        if None in (start_date_raw, end_date_raw):
            raise BrandingMisconfigurationError("Non-fallback event doesn't have start and end dates defined!")

        # We extend the configured month & day with an arbitrary leap year, allowing a datetime object to exist.
        # This may raise errors if misconfigured. We let the caller handle such cases.
        start_date = datetime.strptime(f"{start_date_raw} {ARBITRARY_YEAR}", DATE_FMT).replace(tzinfo=UTC).date()
        end_date = datetime.strptime(f"{end_date_raw} {ARBITRARY_YEAR}", DATE_FMT).replace(tzinfo=UTC).date()

        return MetaFile(is_fallback=False, start_date=start_date, end_date=end_date, description=description)

    async def construct_event(self, directory: RemoteObject) -> Event:
        """
        Construct an `Event` instance from an event `directory`.

        The caller is responsible for handling errors caused by misconfiguration.
        """
        contents = await self.fetch_directory(directory.path)

        missing_assets = {"meta.md", "server_icons", "banners"} - contents.keys()

        if missing_assets:
            raise BrandingMisconfigurationError(f"Directory is missing following assets: {missing_assets}")

        server_icons = await self.fetch_directory(contents["server_icons"].path, types=("file",))
        banners = await self.fetch_directory(contents["banners"].path, types=("file",))

        if len(server_icons) == 0:
            raise BrandingMisconfigurationError("Found no server icons!")
        if len(banners) == 0:
            raise BrandingMisconfigurationError("Found no server banners!")

        meta_bytes = await self.fetch_file(contents["meta.md"].download_url)

        meta_file = self.parse_meta_file(meta_bytes)

        return Event(directory.path, meta_file, list(banners.values()), list(server_icons.values()))

    async def get_events(self) -> list[Event]:
        """
        Discover available events in the branding repository.

        Propagate errors if an event fails to fetch or deserialize.
        """
        log.debug("Discovering events in branding repository.")

        event_directories = await self.fetch_directory("events", types=("dir",))  # Skip files.

        instances: list[Event] = []

        for event_directory in event_directories.values():
            log.trace(f"Reading event directory: '{event_directory.path}'.")
            instance = await self.construct_event(event_directory)
            instances.append(instance)

        return instances

    async def get_current_event(self) -> tuple[Event, list[Event]]:
        """
        Get the currently active event, or the fallback event.

        The second return value is a list of all available events. The caller may discard it, if not needed.
        Returning all events alongside the current one prevents having to query the API twice in some cases.

        Raise an error in the following cases:
          * GitHub request fails
          * The branding repo contains an invalid event
          * No event is active and the fallback event is missing

        Events are validated in the branding repo. The bot assumes that events are valid.
        """
        utc_now = datetime.now(tz=UTC)
        log.debug(f"Finding active event for: {utc_now}.")

        # Construct an object in the arbitrary year for the purpose of comparison.
        lookup_now = date(year=ARBITRARY_YEAR, month=utc_now.month, day=utc_now.day)
        log.trace(f"Lookup object in arbitrary year: {lookup_now}.")

        available_events = await self.get_events()
        log.trace(f"Found {len(available_events)} available events.")

        for event in available_events:
            meta = event.meta
            if meta.is_fallback:
                continue

            start_date, end_date = meta.start_date, meta.end_date

            # Case where the event starts and ends in the same year.
            if start_date <= lookup_now <= end_date:
                return event, available_events

            # Case where the event spans across two years.
            if start_date > end_date and (lookup_now >= start_date or lookup_now <= end_date):
                return event, available_events

        log.trace("No active event found. Looking for fallback event.")

        for event in available_events:
            if event.meta.is_fallback:
                return event, available_events

        raise BrandingMisconfigurationError("No event is active and the fallback event is missing!")
