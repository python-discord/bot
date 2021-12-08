from abc import ABC, abstractmethod
from typing import Dict, Optional

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings import ActionSettings, create_settings


class Filter(ABC):
    """
    A class representing a filter.

    Each filter looks for a specific attribute within an event (such as message sent),
    and defines what action should be performed if it is triggered.
    """

    def __init__(self, filter_data: Dict, action_defaults: Optional[ActionSettings] = None):
        self.id = filter_data["id"]
        self.content = filter_data["content"]
        self.description = filter_data["description"]
        self.actions, self.validations = create_settings(filter_data["settings"])
        if not self.actions:
            self.actions = action_defaults
        elif action_defaults:
            self.actions.fallback_to(action_defaults)
        self.exact = filter_data["additional_field"]

    @abstractmethod
    def triggered_on(self, ctx: FilterContext) -> bool:
        """Search for the filter's content within a given context."""
