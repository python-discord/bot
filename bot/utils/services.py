from aiohttp import ClientConnectorError

import bot
from bot.constants import URLs
from bot.log import get_logger

log = get_logger(__name__)

FAILED_REQUEST_ATTEMPTS = 3
MAX_PASTE_LENGTH = 100_000


class PasteUploadError(Exception):
    """Raised when an error is encountered uploading to the paste service."""


class PasteTooLongError(Exception):
    """Raised when content is too large to upload to the paste service."""


async def send_to_paste_service(contents: str, *, extension: str = "", max_length: int = MAX_PASTE_LENGTH) -> str:
    """
    Upload `contents` to the paste service.

    `extension` is added to the output URL. `max_length` can be used to limit the allowed contents length
    to lower than the maximum allowed by the paste service.

    Raises `PasteTooLongError` if contents is too long to upload, and `PasteUploadError` if uploading fails.

    Returns the generated URL with the extension.
    """
    extension = extension and f".{extension}"

    max_size = min(max_length, MAX_PASTE_LENGTH)
    contents_size = len(contents.encode())
    if contents_size > max_size:
        log.info("Contents too large to send to paste service.")
        raise PasteTooLongError(f"Contents of size {contents_size} greater than maximum size {max_size}")

    log.debug(f"Sending contents of size {contents_size} bytes to paste service.")
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

            paste_link = URLs.paste_service.format(key=response_json['key']) + extension

            if extension == '.py':
                return paste_link

            return paste_link + "?noredirect"

        log.warning(
            f"Got unexpected JSON response from paste service: {response_json}\n"
            f"trying again ({attempt}/{FAILED_REQUEST_ATTEMPTS})."
        )

    raise PasteUploadError("Failed to upload contents to pastebin")
