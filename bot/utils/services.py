import logging
from typing import Optional

from aiohttp import ClientConnectorError

import bot
from bot.constants import URLs

log = logging.getLogger(__name__)

FAILED_REQUEST_ATTEMPTS = 3


async def send_to_paste_service(contents: str, *, extension: str = "") -> Optional[str]:
    """
    Upload `contents` to the paste service.

    `extension` is added to the output URL

    When an error occurs, `None` is returned, otherwise the generated URL with the suffix.
    """
    extension = extension and f".{extension}"
    log.debug(f"Sending contents of size {len(contents.encode())} bytes to paste service.")
    paste_url = URLs.paste_service.format(key="documents")
    for attempt in range(1, FAILED_REQUEST_ATTEMPTS + 1):
        try:
            async with bot.instance.http_session.post(paste_url, data=contents) as response:
                response_json = await response.json()
        except ClientConnectorError:
            log.warning(
                f"Failed to connect to paste service at url {paste_url}, "
                f"trying again ({attempt}/{FAILED_REQUEST_ATTEMPTS})."
            )
            continue
        except Exception:
            log.exception(
                f"An unexpected error has occurred during handling of the request, "
                f"trying again ({attempt}/{FAILED_REQUEST_ATTEMPTS})."
            )
            continue

        if "message" in response_json:
            log.warning(
                f"Paste service returned error {response_json['message']} with status code {response.status}, "
                f"trying again ({attempt}/{FAILED_REQUEST_ATTEMPTS})."
            )
            continue
        elif "key" in response_json:
            log.info(f"Successfully uploaded contents to paste service behind key {response_json['key']}.")
            return URLs.paste_service.format(key=response_json['key']) + extension
        log.warning(
            f"Got unexpected JSON response from paste service: {response_json}\n"
            f"trying again ({attempt}/{FAILED_REQUEST_ATTEMPTS})."
        )
