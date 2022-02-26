from typing import Optional

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._filters.filter import Filter
from bot.exts.filtering._settings import ActionSettings


class InviteFilter(Filter):
    """A filter which looks for invites to a specific guild in messages."""

    def __init__(self, filter_data: dict, action_defaults: Optional[ActionSettings] = None):
        super().__init__(filter_data, action_defaults)
        self.content = int(self.content)

    def triggered_on(self, ctx: FilterContext) -> bool:
        """Searches for a guild ID in the context content, given as a set of IDs."""
        return self.content in ctx.content
