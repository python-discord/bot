import re

from discord.ext.commands import BadArgument

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._filters.filter import Filter

# Maximum perceptual hash difference for positive predictions.
_THRESHOLD = 4
_HEX_RE = re.compile(r"^(?:0x)?([0-9a-fA-F]{1,16})$")


class ImageHashFilter(Filter):
    """A filter which matches image perceptual hashes represented as hexadecimal values."""

    name = "image_hash"

    async def triggered_on(self, ctx: FilterContext) -> bool:
        """Search for a perceptual hash match within a given context of attachment hashes."""
        candidate_hash = int(self.content, 16)

        for image_hash in ctx.content:
            if int.bit_count(image_hash ^ candidate_hash) <= _THRESHOLD:
                ctx.matches.append(f"{image_hash:016x}")
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
