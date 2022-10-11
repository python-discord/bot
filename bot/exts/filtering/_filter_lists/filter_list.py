from abc import abstractmethod
from collections.abc import Iterator
from enum import Enum
from typing import Any, ItemsView, NamedTuple, Optional, Type

from discord.ext.commands import BadArgument

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._filters.filter import Filter
from bot.exts.filtering._settings import ActionSettings, ValidationSettings, create_settings
from bot.exts.filtering._utils import FieldRequiring, past_tense
from bot.log import get_logger

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


def list_type_converter(argument: str) -> ListType:
    """A converter to get the appropriate list type."""
    argument = argument.lower()
    for list_type, list_aliases in aliases:
        if argument in list_aliases or argument in map(past_tense, list_aliases):
            return list_type
    raise BadArgument(f"No matching list type found for {argument!r}.")


class Defaults(NamedTuple):
    """Represents an atomic list's default settings."""

    actions: ActionSettings
    validations: ValidationSettings


class AtomicList(NamedTuple):
    """
    Represents the atomic structure of a single filter list as it appears in the database.

    This is as opposed to the FilterList class which is a combination of several list types.
    """

    id: int
    name: str
    list_type: ListType
    defaults: Defaults
    filters: dict[int, Filter]

    @property
    def label(self) -> str:
        """Provide a short description identifying the list with its name and type."""
        return f"{past_tense(self.list_type.name.lower())} {self.name.lower()}"


class FilterList(FieldRequiring):
    """Dispatches events to lists of _filters, and aggregates the responses into a single list of actions to take."""

    # Each subclass must define a name matching the filter_list name we're expecting to receive from the database.
    # Names must be unique across all filter lists.
    name = FieldRequiring.MUST_SET_UNIQUE

    def __init__(self):
        self._filter_lists: dict[ListType, AtomicList] = {}

    def __iter__(self) -> Iterator[ListType]:
        return iter(self._filter_lists)

    def __getitem__(self, list_type: ListType) -> AtomicList:
        return self._filter_lists[list_type]

    def __contains__(self, list_type: ListType) -> bool:
        return list_type in self._filter_lists

    def __bool__(self) -> bool:
        return bool(self._filter_lists)

    def __len__(self) -> int:
        return len(self._filter_lists)

    def items(self) -> ItemsView[ListType, AtomicList]:
        """Return an iterator for the lists' types and values."""
        return self._filter_lists.items()

    def add_list(self, list_data: dict) -> AtomicList:
        """Add a new type of list (such as a whitelist or a blacklist) this filter list."""
        actions, validations = create_settings(list_data["settings"], keep_empty=True)
        list_type = ListType(list_data["list_type"])
        defaults = Defaults(actions, validations)

        filters = {}
        for filter_data in list_data["filters"]:
            filters[filter_data["id"]] = self._create_filter(filter_data)

        self._filter_lists[list_type] = AtomicList(list_data["id"], self.name, list_type, defaults, filters)
        return self._filter_lists[list_type]

    def remove_list(self, list_type: ListType) -> None:
        """Remove the list associated with the given type from the FilterList object."""
        if list_type not in self._filter_lists:
            return
        self._filter_lists.pop(list_type)

    def default(self, list_type: ListType, setting: str) -> Any:
        """Get the default value of a specific setting."""
        missing = object()
        value = self._filter_lists[list_type].defaults.actions.get_setting(setting, missing)
        if value is missing:
            value = self._filter_lists[list_type].defaults.validations.get_setting(setting, missing)
            if value is missing:
                raise ValueError(f"Could find a setting named {setting}.")
        return value

    def add_filter(self, list_type: ListType, filter_data: dict) -> Filter:
        """Add a filter to the list of the specified type."""
        new_filter = self._create_filter(filter_data)
        self[list_type].filters[filter_data["id"]] = new_filter
        return new_filter

    @abstractmethod
    def get_filter_type(self, content: str) -> Type[Filter]:
        """Get a subclass of filter matching the filter list and the filter's content."""

    @property
    @abstractmethod
    def filter_types(self) -> set[Type[Filter]]:
        """Return the types of filters used by this list."""

    @abstractmethod
    async def actions_for(self, ctx: FilterContext) -> tuple[Optional[ActionSettings], Optional[str]]:
        """Dispatch the given event to the list's filters, and return actions to take and a message to relay to mods."""

    @staticmethod
    def filter_list_result(
        ctx: FilterContext, filters: dict[int, Filter], defaults: ValidationSettings
    ) -> list[Filter]:
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
        passed_by_default, failed_by_default = defaults.evaluate(ctx)
        default_answer = not bool(failed_by_default)

        relevant_filters = []
        for filter_ in filters.values():
            if not filter_.validations:
                if default_answer and filter_.triggered_on(ctx):
                    relevant_filters.append(filter_)
            else:
                passed, failed = filter_.validations.evaluate(ctx)
                if not failed and failed_by_default < passed:
                    if filter_.triggered_on(ctx):
                        relevant_filters.append(filter_)

        return relevant_filters

    def _create_filter(self, filter_data: dict) -> Filter:
        """Create a filter from the given data."""
        try:
            filter_type = self.get_filter_type(filter_data["content"])
            new_filter = filter_type(filter_data)
        except TypeError as e:
            log.warning(e)
        else:
            return new_filter
