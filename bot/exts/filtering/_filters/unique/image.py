import asyncio
import io

import discord
import imagehash
from PIL import Image, UnidentifiedImageError

from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filters.filter import UniqueFilter

_THRESHOLD = 4
_KNOWN_IMAGE_HASHES = [
    imagehash.hex_to_hash(s) for s in [
        # A camera-taken image of a tweet attributed to @MrBeast about the purported launch of a crypto casino;
        # there is a URL in the image that varies by instance
        "c0d08f2f2f60f0cf",
        # An image saying "Activate Code for Bonus!"
        "973c4178e79492cd",
        # An image saying "Withdrawal Success!"
        "817c7e9391e46c1b",
    ]
]


async def _image_is_match(image: Image.Image) -> bool:
    """Return whether the one image matches any of those known to be posted by compromised accounts."""
    incoming_image_hash = await asyncio.to_thread(imagehash.phash, image)
    has_match = any(
        incoming_image_hash - known_image_hash < _THRESHOLD
        for known_image_hash in _KNOWN_IMAGE_HASHES
    )
    return has_match


class ImageFilter(UniqueFilter):
    """Filter messages that contain an image attachment whose perceptual hash matches images associated with scams."""

    name = "image"
    events = (Event.MESSAGE, )

    async def triggered_on(self, ctx: FilterContext) -> bool:
        """Return whether the message has an attached image that is known to be posted by compromised accounts."""
        for attachment in ctx.attachments:
            if (
                attachment.content_type is None
                or not attachment.content_type.startswith("image")
                or attachment.size > 3e7  # 30 mb
            ):
                continue

            try:
                image_bytes = io.BytesIO(await attachment.read())
            except (discord.Forbidden, discord.DiscordServerError, discord.NotFound):
                continue

            try:
                image = await asyncio.to_thread(Image.open, image_bytes)
            except UnidentifiedImageError:
                continue

            if await _image_is_match(image):
                return True

        return False
