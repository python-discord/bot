import logging
import re
import zlib
from collections import defaultdict
from typing import AsyncIterator, DefaultDict, List, Optional, Tuple

import aiohttp

import bot

log = logging.getLogger(__name__)

FAILED_REQUEST_ATTEMPTS = 3
INVENTORY_DICT = DefaultDict[str, List[Tuple[str, str]]]
_V2_LINE_RE = re.compile(r'(?x)(.+?)\s+(\S*:\S*)\s+(-?\d+)\s+?(\S*)\s+(.*)')


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
        buf = b''
        async for chunk in self._read_compressed_chunks():
            buf += chunk
            pos = buf.find(b'\n')
            while pos != -1:
                yield buf[:pos].decode()
                buf = buf[pos + 1:]
                pos = buf.find(b'\n')


async def _load_v1(stream: aiohttp.StreamReader) -> INVENTORY_DICT:
    invdata = defaultdict(list)

    async for line in stream:
        name, type_, location = line.decode().rstrip().split(maxsplit=2)
        # version 1 did not add anchors to the location
        if type_ == 'mod':
            type_ = 'py:module'
            location += '#module-' + name
        else:
            type_ = 'py:' + type_
            location += '#' + name
        invdata[type_].append((name, location))
    return invdata


async def _load_v2(stream: aiohttp.StreamReader) -> INVENTORY_DICT:
    invdata = defaultdict(list)

    async for line in ZlibStreamReader(stream):
        m = _V2_LINE_RE.match(line.rstrip())
        name, type_, _prio, location, _dispname = m.groups()  # ignore the parsed items we don't need
        if location.endswith('$'):
            location = location[:-1] + name

        invdata[type_].append((name, location))
    return invdata


async def _fetch_inventory(url: str) -> INVENTORY_DICT:
    """Fetch, parse and return an intersphinx inventory file from an url."""
    timeout = aiohttp.ClientTimeout(sock_connect=5, sock_read=5)
    async with bot.instance.http_session.get(url, timeout=timeout, raise_for_status=True) as response:
        stream = response.content

        inventory_header = (await stream.readline()).decode().rstrip()
        inventory_version = int(inventory_header[-1:])
        await stream.readline()  # skip project name
        await stream.readline()  # skip project version

        if inventory_version == 1:
            return await _load_v1(stream)

        elif inventory_version == 2:
            if b"zlib" not in await stream.readline():
                raise ValueError(f"Invalid inventory file at url {url}.")
            return await _load_v2(stream)

        raise ValueError(f"Invalid inventory file at url {url}.")


async def fetch_inventory(url: str) -> Optional[INVENTORY_DICT]:
    """Get inventory from `url`, retrying `FAILED_REQUEST_ATTEMPTS` times on errors."""
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
        except Exception:
            log.exception(
                f"An unexpected error has occurred during fetching of {url}; "
                f"trying again ({attempt}/{FAILED_REQUEST_ATTEMPTS})."
            )
        else:
            return inventory

    return None
