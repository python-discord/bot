
import aiohttp

from bot import instance
from bot.constants import Keys, URLs
from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filters.filter import UniqueFilter
from bot.log import get_logger

log = get_logger(__name__)

# Maximum perceptual hash difference for positive predictions
_THRESHOLD = 4
# Maximum number of seconds to wait for Rhodium API
_TIMEOUT = 5

_KNOWN_IMAGE_HASHES = [
    # A camera-taken image of a tweet attributed to @MrBeast about the purported launch of a crypto casino;
    # there is a URL in the image that varies by instance
    219481626328303491,
    # A variant of the previous image where the Twitter/X sidebar is visible
    3558126897613383424,
    # Another variant with different cropping
    -8968981178804062199,
    # A variant with side bars on the left and right
    -2026249180596484892,
    # A variant attributed to Cristiano Ronaldo instead of Mr. Beast
    7197045843299794950,
    # Andrew Tate
    -6841797813482679662,

    # An image saying "Activate Code for Bonus!"
    6997610946676476306,
    # A variant of the previous image with different cropping
    -6531607042796463452,

    # An image saying "Withdrawal Success!"
    -9135984495352994088,

    # A collage of four images, the first being a purported tweet from Elon Musk about the opening a crypto casino,
    # and the rest of similar character to the previous two
    231962884035511073
]


def _is_match(image_hash: int) -> bool:
    return any(
        int.bit_count(image_hash ^ candidate_hash) <= _THRESHOLD
        for candidate_hash in _KNOWN_IMAGE_HASHES
    )

class RhodiumAPIError(Exception):
    """Exception raised when the Rhodium API returns an error."""


async def _get_hash(image_url: str) -> int:
    async with instance.http_session.post(
        url=URLs.rhodium_api,
        headers={"Authorization": f"Bearer {Keys.rhodium}"},
        json={"url": image_url},
        timeout=_TIMEOUT,
    ) as response:
        if response.status != 200:
            contents = await response.text()

            raise RhodiumAPIError(f"Rhodium API returned status code {response.status}: {contents}")

        response_data = await response.json()
        return response_data["i64"]


class ImageFilter(UniqueFilter):
    """Filter messages that contain an image attachment whose perceptual hash matches images associated with scams."""

    name = "image"
    events = (Event.MESSAGE, )

    async def triggered_on(self, ctx: FilterContext) -> bool:
        """Return whether the message has an attached image that is known to be posted by compromised accounts."""
        log.trace("Entering image filter")
        for attachment in ctx.attachments:
            if (
                attachment.content_type is None
                or not attachment.content_type.startswith("image")
                or attachment.size > 5e6  # 5mb
            ):
                continue

            try:
                image_hash = await _get_hash(attachment.url)
            except aiohttp.ClientError:
                log.exception("Unhandled aiohttp exception while getting image hash")
                return False
            except RhodiumAPIError as e:
                log.exception("Rhodium API error: %s", e)
                return False
            except TimeoutError:
                log.exception("Timed out getting image hash")
                return False

            if _is_match(image_hash):
                return True

        return False
