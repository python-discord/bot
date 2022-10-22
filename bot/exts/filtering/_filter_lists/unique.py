from botcore.utils.logging import get_logger
from discord.ext.commands import Cog

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._filter_lists.filter_list import FilterList, ListType, SubscribingAtomicList
from bot.exts.filtering._filters.filter import UniqueFilter
from bot.exts.filtering._filters.unique import unique_filter_types
from bot.exts.filtering._settings import ActionSettings, Defaults, create_settings

log = get_logger(__name__)


class UniquesList(FilterList[UniqueFilter]):
    """
    A list of unique filters.

    Unique filters are ones that should only be run once in a given context.
    Each unique filter subscribes to a subset of events to respond to.
    """

    name = "unique"
    _already_warned = set()

    def __init__(self, filtering_cog: Cog):
        super().__init__()
        self.filtering_cog = filtering_cog  # This is typed as a Cog to avoid a circular import.
        self.loaded_types: dict[str, type[UniqueFilter]] = {}

    def add_list(self, list_data: dict) -> SubscribingAtomicList:
        """Add a new type of list (such as a whitelist or a blacklist) this filter list."""
        actions, validations = create_settings(list_data["settings"], keep_empty=True)
        list_type = ListType(list_data["list_type"])
        defaults = Defaults(actions, validations)
        new_list = SubscribingAtomicList(list_data["id"], self.name, list_type, defaults, {})
        self[list_type] = new_list

        filters = {}
        events = set()
        for filter_data in list_data["filters"]:
            new_filter = self._create_filter(filter_data, defaults)
            if new_filter:
                new_list.subscribe(new_filter, *new_filter.events)
                filters[filter_data["id"]] = new_filter
                self.loaded_types[new_filter.name] = type(new_filter)
                events.update(new_filter.events)

        new_list.filters.update(filters)
        if hasattr(self.filtering_cog, "subscribe"):  # Subscribe the filter list to any new events found.
            self.filtering_cog.subscribe(self, *events)
        return new_list

    def get_filter_type(self, content: str) -> type[UniqueFilter] | None:
        """Get a subclass of filter matching the filter list and the filter's content."""
        try:
            return unique_filter_types[content]
        except KeyError:
            if content not in self._already_warned:
                log.warn(f"A unique filter named {content} was supplied, but no matching implementation found.")
                self._already_warned.add(content)
            return None

    @property
    def filter_types(self) -> set[type[UniqueFilter]]:
        """Return the types of filters used by this list."""
        return set(self.loaded_types.values())

    async def actions_for(self, ctx: FilterContext) -> tuple[ActionSettings | None, list[str]]:
        """Dispatch the given event to the list's filters, and return actions to take and messages to relay to mods."""
        triggers = self[ListType.DENY].filter_list_result(ctx)
        actions = None
        messages = []
        if triggers:
            actions = self[ListType.DENY].merge_actions(triggers)
            messages = self[ListType.DENY].format_messages(triggers)
        return actions, messages
