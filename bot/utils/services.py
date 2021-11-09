import typing
from typing import Optional

import aiohttp
from aiohttp import ClientConnectorError

import bot
from bot.constants import URLs
from bot.log import get_logger

log = get_logger(__name__)
T = typing.TypeVar("T")

FAILED_REQUEST_ATTEMPTS = 3


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
