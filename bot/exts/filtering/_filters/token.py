import re

from discord.ext.commands import BadArgument

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._filters.filter import Filter


class TokenFilter(Filter):
    """A filter which looks for a specific token given by regex."""

    name = "token"

    async def triggered_on(self, ctx: FilterContext) -> bool:
        """Searches for a regex pattern within a given context."""
        pattern = self.content

        match = re.search(pattern, ctx.content, flags=re.IGNORECASE)
        if match:
            ctx.matches.append(match[0])
            return True
        return False

    @classmethod
    async def process_input(cls, content: str, description: str) -> tuple[str, str]:
        """
        Process the content and description into a form which will work with the filtering.

        A BadArgument should be raised if the content can't be used.
        """
        try:
            re.compile(content)
        except re.error as e:
            raise BadArgument(str(e))
        return content, description
