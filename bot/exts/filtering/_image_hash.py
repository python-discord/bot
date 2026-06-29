
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
        hash_hex = response_data.get("hex")
        if not hash_hex:
            raise RhodiumAPIError("Rhodium API response did not include a hex hash.")

        unsigned = int(str(hash_hex).removeprefix("0x"), 16)
        if unsigned >= (1 << 63):
            return unsigned - (1 << 64)
        return unsigned


def signed_i64_to_hex(value: int) -> str:
    """Convert a signed 64-bit integer to a normalized lowercase 16-char hexadecimal string."""
    return f"{value & ((1 << 64) - 1):016x}"
