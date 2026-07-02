
from bot import instance
from bot.constants import Keys, URLs

# Maximum number of seconds to wait for Rhodium API.
_TIMEOUT = 5
# Maximum perceptual hash difference for a positive prediction.
HASH_DISTANCE_THRESHOLD = 4


class RhodiumAPIError(Exception):
    """Exception raised when the Rhodium API returns an error."""


async def get_image_hash(image_url: str) -> int:
    """Return the signed i64 perceptual hash for an image URL from Rhodium."""
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


def signed_i64_to_hex(value: int) -> str:
    """Convert a signed 64-bit integer to a normalized lowercase 16-char hexadecimal string."""
    return f"{value & ((1 << 64) - 1):016x}"


def signed_i64_to_u64(value: int) -> int:
    """Convert a signed 64-bit integer into its unsigned 64-bit representation."""
    return value & ((1 << 64) - 1)
