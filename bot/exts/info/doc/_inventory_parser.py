import re
import zlib
from collections import defaultdict
from collections.abc import AsyncIterator

import aiohttp

import bot
from bot.log import get_logger

log = get_logger(__name__)

FAILED_REQUEST_ATTEMPTS = 3
_V2_LINE_RE = re.compile(r"(?x)(.+?)\s+(\S*:\S*)\s+(-?\d+)\s+?(\S*)\s+(.*)")

InventoryDict = defaultdict[str, list[tuple[str, str]]]


class InvalidHeaderError(Exception):
    """Raised when an inventory file has an invalid header."""


class ZlibStreamReader:
    """Class used for decoding zlib data of a stream line by line."""

    READ_CHUNK_SIZE = 16 * 1024

    def __init__(self, stream: aiohttp.StreamReader) -> None:
        self.stream = stream

    async def _read_compressed_chunks(self) -> AsyncIterator[bytes]:
        """Read zlib data in `READ_CHUNK_SIZE` sized chunks and decompress."""
        decompressor = zlib.decompressobj()
        async for chunk in self.stream.iter_chunked(self.READ_CHUNK_SIZE):
            yield decompressor.decompress(chunk)

        yield decompressor.flush()

    async def __aiter__(self) -> AsyncIterator[str]:
        """Yield lines of decompressed text."""
        buf = b""
        async for chunk in self._read_compressed_chunks():
            buf += chunk
            pos = buf.find(b"\n")
            while pos != -1:
                yield buf[:pos].decode()
                buf = buf[pos + 1:]
                pos = buf.find(b"\n")


async def _load_v1(stream: aiohttp.StreamReader) -> InventoryDict:
    invdata = defaultdict(list)

    async for line in stream:
        name, type_, location = line.decode().rstrip().split(maxsplit=2)
        # version 1 did not add anchors to the location
        if type_ == "mod":
            type_ = "py:module"
            location += "#module-" + name
        else:
            type_ = "py:" + type_
            location += "#" + name
        invdata[type_].append((name, location))
    return invdata


async def _load_v2(stream: aiohttp.StreamReader) -> InventoryDict:
    invdata = defaultdict(list)

    async for line in ZlibStreamReader(stream):
        m = _V2_LINE_RE.match(line.rstrip())

        # If we don't have a match, the package is probably doing something
        # funky with new-lines and we can discount this line, it's likely a
        # multi-line figure description or something similar.
        if not m:
            continue

        name, type_, _prio, location, _dispname = m.groups()  # ignore the parsed items we don't need
        if location.endswith("$"):
            location = location[:-1] + name

        invdata[type_].append((name, location))
    return invdata


async def _fetch_inventory(url: str) -> InventoryDict:
    """Fetch, parse and return an intersphinx inventory file from an url."""
    timeout = aiohttp.ClientTimeout(sock_connect=5, sock_read=5)
    async with bot.instance.http_session.get(url, timeout=timeout, raise_for_status=True) as response:
        stream = response.content

        inventory_header = (await stream.readline()).decode().rstrip()
        try:
            inventory_version = int(inventory_header[-1:])
        except ValueError:
            raise InvalidHeaderError("Unable to convert inventory version header.")

        has_project_header = (await stream.readline()).startswith(b"# Project")
        has_version_header = (await stream.readline()).startswith(b"# Version")
        if not (has_project_header and has_version_header):
            raise InvalidHeaderError("Inventory missing project or version header.")

        if inventory_version == 1:
            return await _load_v1(stream)

        if inventory_version == 2:
            if b"zlib" not in await stream.readline():
                raise InvalidHeaderError("'zlib' not found in header of compressed inventory.")
            return await _load_v2(stream)

        raise InvalidHeaderError("Incompatible inventory version.")


async def fetch_inventory(url: str) -> InventoryDict | None:
    """
    Get an inventory dict from `url`, retrying `FAILED_REQUEST_ATTEMPTS` times on errors.

    `url` should point at a valid sphinx objects.inv inventory file, which will be parsed into the
    inventory dict in the format of {"domain:role": [("symbol_name", "relative_url_to_symbol"), ...], ...}
    """
    for attempt in range(1, FAILED_REQUEST_ATTEMPTS+1):
        try:
            inventory = await _fetch_inventory(url)
        except aiohttp.ClientConnectorError:
            log.warning(
                f"Failed to connect to inventory url at {url}; "
                f"trying again ({attempt}/{FAILED_REQUEST_ATTEMPTS})."
            )
        except aiohttp.ClientError:
            log.error(
                f"Failed to get inventory from {url}; "
                f"trying again ({attempt}/{FAILED_REQUEST_ATTEMPTS})."
            )
        except InvalidHeaderError:
            raise
        except Exception:
            log.exception(
                f"An unexpected error has occurred during fetching of {url}; "
                f"trying again ({attempt}/{FAILED_REQUEST_ATTEMPTS})."
            )
        else:
            return inventory

    return None
