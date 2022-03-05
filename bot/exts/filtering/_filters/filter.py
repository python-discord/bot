from abc import abstractmethod
from typing import Optional

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings import ActionSettings, create_settings
from bot.exts.filtering._utils import FieldRequiring


class Filter(FieldRequiring):
    """
    A class representing a filter.

    Each filter looks for a specific attribute within an event (such as message sent),
    and defines what action should be performed if it is triggered.
    """

    # Each subclass must define a name which will be used to fetch its description.
    # Names must be unique across all types of filters.
    name = FieldRequiring.MUST_SET_UNIQUE
    # If a subclass uses extra fields, it should assign the pydantic model type to this variable.
    extra_fields_type = None

    def __init__(self, filter_data: dict, action_defaults: Optional[ActionSettings] = None):
        self.id = filter_data["id"]
        self.content = filter_data["content"]
        self.description = filter_data["description"]
        self.actions, self.validations = create_settings(filter_data["settings"])
        if not self.actions:
            self.actions = action_defaults
        elif action_defaults:
            self.actions.fallback_to(action_defaults)
        self.extra_fields = filter_data["additional_field"] or "{}"  # noqa: P103
        if self.extra_fields_type:
            self.extra_fields = self.extra_fields_type.parse_raw(self.extra_fields)

    @abstractmethod
    def triggered_on(self, ctx: FilterContext) -> bool:
        """Search for the filter's content within a given context."""

    def __str__(self) -> str:
        """A string representation of the filter."""
        string = f"#{self.id}. `{self.content}`"
        if self.description:
            string += f" - {self.description}"
        return string
