import dataclasses
import datetime
import json
import typing
from typing import Optional

import aiohttp
from aiohttp import ClientConnectorError
from async_rediscache import RedisCache

import bot
from bot.constants import URLs
from bot.log import get_logger

log = get_logger(__name__)
T = typing.TypeVar("T")

FAILED_REQUEST_ATTEMPTS = 3

UNFURL_CACHE = RedisCache(namespace="UnfurledRedirects")
CACHE_LENGTH = datetime.timedelta(days=1)


@dataclasses.dataclass()
class _UnfurlReturn:
    """The return value for the URL unfurling utility."""

    destination: Optional[str] = None
    depth: Optional[int] = None
    error: Optional[str] = None
    created_at: Optional[datetime.datetime] = None


_CONTINUE_RETURN = tuple[str, int]
_JOIN_RETURNS = typing.Union[tuple[_UnfurlReturn, int], _CONTINUE_RETURN, None]


async def _attempt_request(
    url: str,
    attempts: int,
    *,
    method: str = aiohttp.hdrs.METH_POST,
    callback: Optional[typing.Callable[[aiohttp.ClientResponse, int, int], typing.Awaitable[T]]] = None,
    **kw_data,
) -> Optional[typing.Union[aiohttp.ClientResponse, T]]:
    """
    Attempt to perform a request to `url`, `attempt` times, and return the response.

    Make sure to close

    `data` and `kw_data` are passed to the request as is.
    Return None for failures.

    If callback is not None, return the result of calling that instead.
    Callbacks that return None will also be reattempted in the same fashion as the request.
    Callback is called with (response, current_attempt, max_attempts)
    """
    for attempt in range(1, attempts + 1):
        try:
            response = await bot.instance.http_session.request(method, url, **kw_data)

            if callback is None:
                return response
            elif (result := await callback(response, attempt, attempts)) is not None:
                return result

        except ClientConnectorError:
            log.warning(
                f"Failed to connect to service at url {url}, "
                f"trying again ({attempt}/{attempts})."
            )
            continue
        except Exception:
            log.exception(
                f"An unexpected error has occurred during handling of the request, "
                f"trying again ({attempt}/{attempts})."
            )
            continue


async def send_to_paste_service(contents: str, *, extension: str = "") -> Optional[str]:
    """
    Upload `contents` to the paste service.

    `extension` is added to the output URL

    When an error occurs, `None` is returned, otherwise the generated URL with the suffix.
    """
    extension = extension and f".{extension}"
    log.debug(f"Sending contents of size {len(contents.encode())} bytes to paste service.")
    paste_url = URLs.paste_service.format(key="documents")

    async def _callback(_response: aiohttp.ClientResponse, _attempt: int, _attempts: int) -> Optional[str]:
        response_json = await _response.json()

        if "message" in response_json:
            log.warning(
                f"Paste service returned error {response_json['message']} with status code {_response.status}, "
                f"trying again ({_attempt}/{_attempts})."
            )
            return

        elif "key" in response_json:
            log.info(f"Successfully uploaded contents to paste service behind key {response_json['key']}.")

            paste_link = URLs.paste_service.format(key=response_json['key']) + extension

            if extension == '.py':
                return paste_link

            return paste_link + "?noredirect"

        log.warning(
            f"Got unexpected JSON response from paste service: {response_json}\n"
            f"trying again ({_attempt}/{_attempts})."
        )

    return await _attempt_request(paste_url, FAILED_REQUEST_ATTEMPTS, data=contents, callback=_callback)


async def _get_url_from_cache(url: str) -> Optional[_UnfurlReturn]:
    """Return an unfurled URL from cache, or None if it doesn't exist or is expired."""
    cached = await UNFURL_CACHE.get(url)

    if cached is not None:
        log.trace(f"Found hit for URL ({log}) in unfurl cache.")
        data = json.loads(cached)
        expiry = datetime.datetime.fromisoformat(data["expiry"])

        if expiry < datetime.datetime.utcnow():
            # Cache expired, remove it and continue normally
            log.debug(f"Cache entry for ({url}) expired, deleting.")
            await UNFURL_CACHE.delete(url)
        else:
            # Found unexpired hit
            return _UnfurlReturn(data["destination"], data["depth"], None, expiry - CACHE_LENGTH)


async def _unfurl_url(url: str, redirects: int, continues: int, max_continues: int) -> _JOIN_RETURNS:
    """
    The actual core logic of the unfurling.

    Unlike the public utility, this will only follow one redirect, and parse the results.
    The handling of the results is managed by the public function.

    Returns a tuple with a final UnfurlReturn and response status,
    or a tuple containing data to allow the caller to continue, or None.
    """
    # See link for documentation on how to use the worker
    # https://github.com/python-discord/workers/tree/main/url-unfurler
    response = await _attempt_request(URLs.unfurl_worker, 3, json={"url": url}, raise_for_status=False)

    if response is None:
        return

    if response.status == 200:
        # Success, return the destination
        content = await response.json()
        now = datetime.datetime.utcnow()
        return _UnfurlReturn(content["destination"], redirects + content["depth"], None, now), response.status

    elif response.status == 400:
        # Unrecoverable error with the URL used for this unfurling
        error_message = (await response.json())["error"]
        log.warning(f"Failed to unfurl URL ({url}) with error message: {error_message}")
        return _UnfurlReturn(error=error_message), response.status

    elif response.status == 416:
        # Max depth reached by the worker, try again or exit
        data = await response.json()

        if continues < max_continues:
            # Try again (the caller will make a new call with the next URL)
            log.debug(
                f"Hit maximum depth while unfurling URL ({url}) after {data['depth']} attempts. "
                f"Last request was made to ({data['final']}), and next request will be made to {data['next']}. "
                f"{continues + 1}/{max_continues} failures."
            )

            return data["next"], data["depth"]

        else:
            # Give up
            redirects += data["depth"]
            log.info(f"Failed to unfurl URL ({url}) after {redirects} redirects.")
            return _UnfurlReturn(data["next"], redirects, data["error"]), response.status

    elif response.status == 418:
        # The redirect chain has a broken link, can not continue
        data = await response.json()
        redirects += data["depth"]

        log.warning(
            f"Failed to unfurl URL ({url}) due to a broken link in the chain. "
            f"Followed {redirects} redirects, and stopped at ({data['final']})."
        )
        return _UnfurlReturn(data["final"], redirects, data["error"]), response.status

    else:
        response.raise_for_status()


async def unfurl_url(url: str, *, max_continues: int = 0, use_cache: bool = True) -> Optional[_UnfurlReturn]:
    """
    Follow all redirects of a URL, and return the final address.

    Returns an object containing the final URL, number of redirects, error text, and date of last fetch.
    Returns None if we couldn't resolve the URL for any reason.

    The error in the return is only set if the operation failed.
    If false, the final destination might not be accurate, and the date will be None.

    If the worker errors out due to too many redirects,
    we'll attempt to continue from the last URL `max_continues` times.
    """
    next_url = url
    redirects = 0
    continues = 0

    if not use_cache:
        log.info(f"Skipping cache for URL unfurling ({url})")

    while True:
        # Check if we can just use the cache
        if use_cache and (hit := await _get_url_from_cache(next_url)) is not None:
            return hit

        response = await _unfurl_url(next_url, redirects, continues, max_continues)

        if response is None:
            # We couldn't resolve this URL
            return response

        elif isinstance(response[0], _UnfurlReturn):
            # We reached a final conclusion for this URL
            if response[1] == 200:
                # Success, write to cache and return
                data = {
                    "destination": response[0].destination,
                    "depth": response[0].depth,
                    "expiry": (response[0].created_at + CACHE_LENGTH).isoformat()
                }

                # Write to cache and return results
                log.trace(f"Writing URL ({url}) to unfurl CACHE.")
                await UNFURL_CACHE.set(url, json.dumps(data))

            return response[0]

        else:
            next_url = response[0]
            redirects += response[1] + 1
            continues += 1
