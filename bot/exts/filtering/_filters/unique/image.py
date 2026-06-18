import os

import bot
from bot import constants
from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filters.filter import UniqueFilter
from bot.log import get_logger

log = get_logger(__name__)

_THRESHOLD = 4
# Maximum number of seconds to wait for Rhodium API
_TIMEOUT = 0.5
_KNOWN_IMAGE_HASHES = [
    # A camera-taken image of a tweet attributed to @MrBeast about the purported launch of a crypto casino;
    # there is a URL in the image that varies by instance
    219481626328303491,
    # An image saying "Activate Code for Bonus!"
    6997610946676476306,
    # An image saying "Withdrawal Success!"
    -9135984495352994088,
]


def _hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _is_similar(hash_a: int, hash_b: int, max_distance: int = 3) -> bool:
    return _hamming_distance(hash_a, hash_b) <= max_distance


def _is_match(image_hash: int) -> bool:
    return any(
        _is_similar(image_hash, candidate_hash, max_distance=_THRESHOLD)
        for candidate_hash in _KNOWN_IMAGE_HASHES
    )


async def _get_hash(image_url: str) -> int:
    async with bot.instance.http_session.post(
        url=constants.URLs.rhodium_api,
        headers={"Authorization": f"Bearer {os.getenv('RHODIUM_AUTH_TOKEN')}"},
        data=image_url,
        timeout=_TIMEOUT,
    ) as response:
        response.raise_for_status()
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

            image_hash = await _get_hash(attachment.url)
            if _is_match(image_hash):
                return True

        return False
