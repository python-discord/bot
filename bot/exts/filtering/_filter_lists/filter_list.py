import dataclasses
import typing
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from functools import reduce
from typing import Any

import arrow
from discord.ext.commands import BadArgument, Context, Converter

from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filters.filter import Filter, UniqueFilter
from bot.exts.filtering._settings import ActionSettings, Defaults, create_settings
from bot.exts.filtering._utils import FieldRequiring, past_tense
from bot.log import get_logger

if typing.TYPE_CHECKING:
    from bot.exts.filtering.filtering import Filtering

log = get_logger(__name__)


class ListType(Enum):
    """An enumeration of list types."""

    DENY = 0
    ALLOW = 1


#  Alternative names with which each list type can be specified in commands.
aliases = (
    (ListType.DENY, {"deny", "blocklist", "blacklist", "denylist", "bl", "dl"}),
    (ListType.ALLOW, {"allow", "allowlist", "whitelist", "al", "wl"})
)


class ListTypeConverter(Converter):
    """A converter to get the appropriate list type."""

    async def convert(self, ctx: Context, argument: str) -> ListType:
        argument = argument.lower()
        for list_type, list_aliases in aliases:
            if argument in list_aliases or argument in map(past_tense, list_aliases):
                return list_type
        raise BadArgument(f"No matching list type found for {argument!r}.")


# AtomicList and its subclasses must have eq=False, otherwise the dataclass deco will replace the hash function.
@dataclass(frozen=True, eq=False)
class AtomicList:
    """
    Represents the atomic structure of a single filter list as it appears in the database.

    This is as opposed to the FilterList class which is a combination of several list types.
    """

    id: int
    created_at: arrow.Arrow
    updated_at: arrow.Arrow
    name: str
    list_type: ListType
    defaults: Defaults
    filters: dict[int, Filter]

    @property
    def label(self) -> str:
        """Provide a short description identifying the list with its name and type."""
        return f"{past_tense(self.list_type.name.lower())} {self.name.lower()}"

    async def filter_list_result(self, ctx: FilterContext) -> list[Filter]:
        """
        Sift through the list of filters, and return only the ones which apply to the given context.

        The strategy is as follows:
        1. The default settings are evaluated on the given context. The default answer for whether the filter is
        relevant in the given context is whether there aren't any validation settings which returned False.
        2. For each filter, its overrides are considered:
            - If there are no overrides, then the filter is relevant if that is the default answer.
            - Otherwise it is relevant if there are no failed overrides, and any failing default is overridden by a
            successful override.

        If the filter is relevant in context, see if it actually triggers.
        """
        return await self._create_filter_list_result(ctx, self.defaults, self.filters.values())

    async def _create_filter_list_result(
        self, ctx: FilterContext, defaults: Defaults, filters: Iterable[Filter]
    ) -> list[Filter]:
        """A helper function to evaluate the result of `filter_list_result`."""
        passed_by_default, failed_by_default = defaults.validations.evaluate(ctx)
        default_answer = not bool(failed_by_default)

        relevant_filters = []
        for filter_ in filters:
            if not filter_.validations:
                if default_answer and await filter_.triggered_on(ctx):
                    relevant_filters.append(filter_)
            else:
                passed, failed = filter_.validations.evaluate(ctx)
                if not failed and failed_by_default < passed:
                    if await filter_.triggered_on(ctx):
                        relevant_filters.append(filter_)

        if ctx.event == Event.MESSAGE_EDIT and ctx.message and self.list_type == ListType.DENY:
            previously_triggered = ctx.message_cache.get_message_metadata(ctx.message.id)
            # The message might not be cached.
            if previously_triggered and self in previously_triggered:
                ignore_filters = previously_triggered[self]
                # This updates the cache. Some filters are ignored, but they're necessary if there's another edit.
                previously_triggered[self] = relevant_filters
                relevant_filters = [filter_ for filter_ in relevant_filters if filter_ not in ignore_filters]
        return relevant_filters

    def default(self, setting_name: str) -> Any:
        """Get the default value of a specific setting."""
        missing = object()
        value = self.defaults.actions.get_setting(setting_name, missing)
        if value is missing:
            value = self.defaults.validations.get_setting(setting_name, missing)
            if value is missing:
                raise ValueError(f"Couldn't find a setting named {setting_name!r}.")
        return value

    def merge_actions(self, filters: list[Filter]) -> ActionSettings | None:
        """
        Merge the settings of the given filters, with the list's defaults as fallback.

        If `merge_default` is True, include it in the merge instead of using it as a fallback.
        """
        if not filters:  # Nothing to action.
            return None
        try:
            return reduce(
                ActionSettings.union, (filter_.actions or self.defaults.actions for filter_ in filters)
            ).fallback_to(self.defaults.actions)
        except TypeError:
            # The sequence fed to reduce is empty, meaning none of the filters have actions,
            # meaning they all use the defaults.
            return self.defaults.actions

    @staticmethod
    def format_messages(triggers: list[Filter], *, expand_single_filter: bool = True) -> list[str]:
        """Convert the filters into strings that can be added to the alert embed."""
        if len(triggers) == 1 and expand_single_filter:
            message = f"#{triggers[0].id} (`{triggers[0].content}`)"
            if triggers[0].description:
                message += f" - {triggers[0].description}"
            messages = [message]
        else:
            messages = [f"{filter_.id} (`{filter_.content}`)" for filter_ in triggers]
        return messages

    def __hash__(self):
        return hash(id(self))


T = typing.TypeVar("T", bound=Filter)


class FilterList(dict[ListType, AtomicList], typing.Generic[T], FieldRequiring):
    """Dispatches events to lists of _filters, and aggregates the responses into a single list of actions to take."""

    # Each subclass must define a name matching the filter_list name we're expecting to receive from the database.
    # Names must be unique across all filter lists.
    name = FieldRequiring.MUST_SET_UNIQUE

    _already_warned = set()

    def add_list(self, list_data: dict) -> AtomicList:
        """Add a new type of list (such as a whitelist or a blacklist) this filter list."""
        actions, validations = create_settings(list_data["settings"], keep_empty=True)
        list_type = ListType(list_data["list_type"])
        defaults = Defaults(actions, validations)

        filters = {}
        for filter_data in list_data["filters"]:
            new_filter = self._create_filter(filter_data, defaults)
            if new_filter:
                filters[filter_data["id"]] = new_filter

        self[list_type] = AtomicList(
            list_data["id"],
            arrow.get(list_data["created_at"]),
            arrow.get(list_data["updated_at"]),
            self.name,
            list_type,
            defaults,
            filters
        )
        return self[list_type]

    def add_filter(self, list_type: ListType, filter_data: dict) -> T | None:
        """Add a filter to the list of the specified type."""
        new_filter = self._create_filter(filter_data, self[list_type].defaults)
        if new_filter:
            self[list_type].filters[filter_data["id"]] = new_filter
        return new_filter

    @abstractmethod
    def get_filter_type(self, content: str) -> type[T]:
        """Get a subclass of filter matching the filter list and the filter's content."""

    @property
    @abstractmethod
    def filter_types(self) -> set[type[T]]:
        """Return the types of filters used by this list."""

    @abstractmethod
    async def actions_for(
        self, ctx: FilterContext
    ) -> tuple[ActionSettings | None, list[str], dict[ListType, list[Filter]]]:
        """Dispatch the given event to the list's filters, and return actions to take and messages to relay to mods."""

    def _create_filter(self, filter_data: dict, defaults: Defaults) -> T | None:
        """Create a filter from the given data."""
        try:
            content = filter_data["content"]
            filter_type = self.get_filter_type(content)
            if filter_type:
                return filter_type(filter_data, defaults)
            if content not in self._already_warned:
                log.warning(f"A filter named {content} was supplied, but no matching implementation found.")
                self._already_warned.add(content)
            return None
        except TypeError as e:
            log.warning(e)

    def __hash__(self):
        return hash(id(self))


@dataclass(frozen=True, eq=False)
class SubscribingAtomicList(AtomicList):
    """
    A base class for a list of unique filters.

    Unique filters are ones that should only be run once in a given context.
    Each unique filter is subscribed to a subset of events to respond to.
    """

    subscriptions: defaultdict[Event, list[int]] = dataclasses.field(default_factory=lambda: defaultdict(list))

    def subscribe(self, filter_: UniqueFilter, *events: Event) -> None:
        """
        Subscribe a unique filter to the given events.

        The filter is added to a list for each event. When the event is triggered, the filter context will be
        dispatched to the subscribed filters.
        """
        for event in events:
            if filter_ not in self.subscriptions[event]:
                self.subscriptions[event].append(filter_.id)

    async def filter_list_result(self, ctx: FilterContext) -> list[Filter]:
        """Sift through the list of filters, and return only the ones which apply to the given context."""
        event_filters = [self.filters[id_] for id_ in self.subscriptions[ctx.event]]
        return await self._create_filter_list_result(ctx, self.defaults, event_filters)


class UniquesListBase(FilterList[UniqueFilter], ABC):
    """
    A list of unique filters.

    Unique filters are ones that should only be run once in a given context.
    Each unique filter subscribes to a subset of events to respond to.
    """

    def __init__(self, filtering_cog: "Filtering"):
        super().__init__()
        self.filtering_cog = filtering_cog
        self.loaded_types: dict[str, type[UniqueFilter]] = {}

    def add_list(self, list_data: dict) -> SubscribingAtomicList:
        """Add a new type of list (such as a whitelist or a blacklist) this filter list."""
        actions, validations = create_settings(list_data["settings"], keep_empty=True)
        list_type = ListType(list_data["list_type"])
        defaults = Defaults(actions, validations)
        new_list = SubscribingAtomicList(
            list_data["id"],
            arrow.get(list_data["created_at"]),
            arrow.get(list_data["updated_at"]),
            self.name,
            list_type,
            defaults,
            {}
        )
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

    @property
    def filter_types(self) -> set[type[UniqueFilter]]:
        """Return the types of filters used by this list."""
        return set(self.loaded_types.values())
