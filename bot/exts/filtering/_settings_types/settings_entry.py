from __future__ import annotations

from abc import abstractmethod
from typing import Any, ClassVar, Self

from pydantic import BaseModel, PrivateAttr

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._utils import FieldRequiring


class SettingsEntry(BaseModel, FieldRequiring):
    """
    A basic entry in the settings field appearing in every filter list and filter.

    For a filter list, this is the default setting for it. For a filter, it's an override of the default entry.
    """

    # Each subclass must define a name matching the entry name we're expecting to receive from the database.
    # Names must be unique across all filter lists.
    name: ClassVar[str] = FieldRequiring.MUST_SET_UNIQUE
    # Each subclass must define a description of what it does. If the data an entry type receives comprises
    # several DB fields, the value should a dictionary of field names and their descriptions.
    description: ClassVar[str | dict[str, str]] = FieldRequiring.MUST_SET

    _overrides: set[str] = PrivateAttr(default_factory=set)

    def __init__(self, defaults: SettingsEntry | None = None, /, **data):
        overrides = set()
        if defaults:
            defaults_dict = defaults.model_dump()
            for field_name, field_value in list(data.items()):
                if field_value is None:
                    data[field_name] = defaults_dict[field_name]
                else:
                    overrides.add(field_name)
        super().__init__(**data)
        self._overrides |= overrides

    @property
    def overrides(self) -> dict[str, Any]:
        """Return a dictionary of overrides."""
        return {name: getattr(self, name) for name in self._overrides}

    @classmethod
    def create(
        cls, entry_data: dict[str, Any] | None, *, defaults: SettingsEntry | None = None, keep_empty: bool = False
    ) -> SettingsEntry | None:
        """
        Returns a SettingsEntry object from `entry_data` if it holds any value, None otherwise.

        Use this method to create SettingsEntry objects instead of the init.
        The None value is significant for how a filter list iterates over its filters.
        """
        if entry_data is None:
            return None
        if not keep_empty and hasattr(entry_data, "values") and all(value is None for value in entry_data.values()):
            return None

        if not isinstance(entry_data, dict):
            entry_data = {cls.name: entry_data}
        return cls(defaults, **entry_data)


class ValidationEntry(SettingsEntry):
    """A setting entry to validate whether the filter should be triggered in the given context."""

    @abstractmethod
    def triggers_on(self, ctx: FilterContext) -> bool:
        """Return whether the filter should be triggered with this setting in the given context."""
        ...


class ActionEntry(SettingsEntry):
    """A setting entry defining what the bot should do if the filter it belongs to is triggered."""

    @abstractmethod
    async def action(self, ctx: FilterContext) -> None:
        """Execute an action that should be taken when the filter this setting belongs to is triggered."""
        ...

    @abstractmethod
    def union(self, other: Self) -> Self:
        """
        Combine two actions of the same type. Each type of action is executed once per filter.

        The following condition must hold: if self == other, then self | other == self.
        """
        ...
