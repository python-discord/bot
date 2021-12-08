import re

from bot.exts.filtering._filters.filter import Filter
from bot.exts.filtering._filter_context import FilterContext


class TokenFilter(Filter):
    """A filter which looks for a specific token given by regex."""

    def triggered_on(self, ctx: FilterContext) -> bool:
        """Searches for a regex pattern within a given context."""
        pattern = self.content

        match = re.search(pattern, ctx.content, flags=re.IGNORECASE)
        if match:
            ctx.matches.append(match[0])
            return True
        return False


