import re

from discord.ext.commands import BadArgument

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._filters.filter import Filter
from bot.exts.filtering._image_hash import HASH_DISTANCE_THRESHOLD, signed_i64_to_u64

_HEX_RE = re.compile(r"^(?:0x)?([0-9a-fA-F]{1,16})$")


class ImageHashFilter(Filter):
    """A filter which matches image perceptual hashes represented as hexadecimal values."""

    name = "image_hash"

    async def triggered_on(self, ctx: FilterContext) -> bool:
        """Search for a perceptual hash match within a given context of attachment hashes."""
        candidate_hash = int(self.content, 16)

        for image_hash in ctx.content:
            normalized_image_hash = signed_i64_to_u64(image_hash)
            distance = int.bit_count(normalized_image_hash ^ candidate_hash)
            if distance <= HASH_DISTANCE_THRESHOLD:
                ctx.matches.append(f"{normalized_image_hash:016x}")
                ctx.filter_info[self] = str(distance)
                return True
        return False

    @classmethod
    async def process_input(cls, content: str, description: str) -> tuple[str, str]:
        """
        Process the content and description into a form which will work with the filtering.

        A BadArgument should be raised if the content can't be used.
        """
        match = _HEX_RE.fullmatch(content.strip())
        if not match:
            raise BadArgument("Image hash content must be hexadecimal (optionally prefixed with `0x`).")

        normalized = f"{int(match.group(1), 16):016x}"
        return normalized, description
