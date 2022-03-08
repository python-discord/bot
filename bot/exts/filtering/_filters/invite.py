from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._filters.filter import Filter


class InviteFilter(Filter):
    """
    A filter which looks for invites to a specific guild in messages.

    The filter stores the guild ID which is allowed or denied.
    """

    name = "invite"

    def __init__(self, filter_data: dict):
        super().__init__(filter_data)
        self.content = int(self.content)

    def triggered_on(self, ctx: FilterContext) -> bool:
        """Searches for a guild ID in the context content, given as a set of IDs."""
        return self.content in ctx.content
