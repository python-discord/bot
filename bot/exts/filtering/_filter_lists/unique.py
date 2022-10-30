from botcore.utils.logging import get_logger

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._filter_lists.filter_list import ListType, UniquesListBase
from bot.exts.filtering._filters.filter import UniqueFilter
from bot.exts.filtering._filters.unique import unique_filter_types
from bot.exts.filtering._settings import ActionSettings

log = get_logger(__name__)


class UniquesList(UniquesListBase):
    """
    A list of unique filters.

    Unique filters are ones that should only be run once in a given context.
    Each unique filter subscribes to a subset of events to respond to.
    """

    name = "unique"

    def get_filter_type(self, content: str) -> type[UniqueFilter] | None:
        """Get a subclass of filter matching the filter list and the filter's content."""
        try:
            return unique_filter_types[content]
        except KeyError:
            if content not in self._already_warned:
                log.warn(f"A unique filter named {content} was supplied, but no matching implementation found.")
                self._already_warned.add(content)
            return None

    async def actions_for(self, ctx: FilterContext) -> tuple[ActionSettings | None, list[str]]:
        """Dispatch the given event to the list's filters, and return actions to take and messages to relay to mods."""
        triggers = self[ListType.DENY].filter_list_result(ctx)
        actions = None
        messages = []
        if triggers:
            actions = self[ListType.DENY].merge_actions(triggers)
            messages = self[ListType.DENY].format_messages(triggers)
        return actions, messages
