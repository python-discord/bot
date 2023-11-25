from __future__ import annotations

import operator
import traceback
from abc import abstractmethod
from copy import copy
from functools import reduce
from typing import Any, NamedTuple, Self, TypeVar

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings_types import settings_types
from bot.exts.filtering._settings_types.settings_entry import ActionEntry, SettingsEntry, ValidationEntry
from bot.exts.filtering._utils import FieldRequiring
from bot.log import get_logger

TSettings = TypeVar("TSettings", bound="Settings")

log = get_logger(__name__)

_already_warned: set[str] = set()

T = TypeVar("T", bound=SettingsEntry)


def create_settings(
    settings_data: dict, *, defaults: Defaults | None = None, keep_empty: bool = False
) -> tuple[ActionSettings | None, ValidationSettings | None]:
    """
    Create and return instances of the Settings subclasses from the given data.

    Additionally, warn for data entries with no matching class.

    In case these are setting overrides, the defaults can be provided to keep track of the correct values.
    """
    action_data = {}
    validation_data = {}
    for entry_name, entry_data in settings_data.items():
        if entry_name in settings_types["ActionEntry"]:
            action_data[entry_name] = entry_data
        elif entry_name in settings_types["ValidationEntry"]:
            validation_data[entry_name] = entry_data
        elif entry_name not in _already_warned:
            log.warning(
                f"A setting named {entry_name} was loaded from the database, but no matching class."
            )
            _already_warned.add(entry_name)
    if defaults is None:
        default_actions = None
        default_validations = None
    else:
        default_actions, default_validations = defaults
    return (
        ActionSettings.create(action_data, defaults=default_actions, keep_empty=keep_empty),
        ValidationSettings.create(validation_data, defaults=default_validations, keep_empty=keep_empty)
    )


class Settings(FieldRequiring, dict[str, T]):
    """
    A collection of settings.

    For processing the settings parts in the database and evaluating them on given contexts.

    Each filter list and filter has its own settings.

    A filter doesn't have to have its own settings. For every undefined setting, it falls back to the value defined in
    the filter list which contains the filter.
    """

    entry_type: type[T]

    _already_warned: set[str] = set()

    @abstractmethod  # ABCs have to have at least once abstract method to actually count as such.
    def __init__(self, settings_data: dict, *, defaults: Settings | None = None, keep_empty: bool = False):
        super().__init__()

        entry_classes = settings_types.get(self.entry_type.__name__)
        for entry_name, entry_data in settings_data.items():
            try:
                entry_cls = entry_classes[entry_name]
            except KeyError:
                if entry_name not in self._already_warned:
                    log.warning(
                        f"A setting named {entry_name} was loaded from the database, "
                        f"but no matching {self.entry_type.__name__} class."
                    )
                    self._already_warned.add(entry_name)
            else:
                try:
                    entry_defaults = None if defaults is None else defaults[entry_name]
                    new_entry = entry_cls.create(
                        entry_data, defaults=entry_defaults, keep_empty=keep_empty
                    )
                    if new_entry:
                        self[entry_name] = new_entry
                except TypeError as e:
                    raise TypeError(
                        f"Attempted to load a {entry_name} setting, but the response is malformed: {entry_data}"
                    ) from e

    @property
    def overrides(self) -> dict[str, Any]:
        """Return a dictionary of overrides across all entries."""
        return reduce(operator.or_, (entry.overrides for entry in self.values() if entry), {})

    def copy(self: TSettings) -> TSettings:
        """Create a shallow copy of the object."""
        return copy(self)

    def get_setting(self, key: str, default: Any | None = None) -> Any:
        """Get the setting matching the key, or fall back to the default value if the key is missing."""
        for entry in self.values():
            if hasattr(entry, key):
                return getattr(entry, key)
        return default

    @classmethod
    def create(
        cls, settings_data: dict, *, defaults: Settings | None = None, keep_empty: bool = False
    ) -> Settings | None:
        """
        Returns a Settings object from `settings_data` if it holds any value, None otherwise.

        Use this method to create Settings objects instead of the init.
        The None value is significant for how a filter list iterates over its filters.
        """
        settings = cls(settings_data, defaults=defaults, keep_empty=keep_empty)
        # If an entry doesn't hold any values, its `create` method will return None.
        # If all entries are None, then the settings object holds no values.
        if not keep_empty and not any(settings.values()):
            return None

        return settings


class ValidationSettings(Settings[ValidationEntry]):
    """
    A collection of validation settings.

    A filter is triggered only if all of its validation settings (e.g whether to invoke in DM) approve
    (the check returns True).
    """

    entry_type = ValidationEntry

    def __init__(self, settings_data: dict, *, defaults: Settings | None = None, keep_empty: bool = False):
        super().__init__(settings_data, defaults=defaults, keep_empty=keep_empty)

    def evaluate(self, ctx: FilterContext) -> tuple[set[str], set[str]]:
        """Evaluates for each setting whether the context is relevant to the filter."""
        passed = set()
        failed = set()

        for name, validation in self.items():
            if validation:
                if validation.triggers_on(ctx):
                    passed.add(name)
                else:
                    failed.add(name)

        return passed, failed


class ActionSettings(Settings[ActionEntry]):
    """
    A collection of action settings.

    If a filter is triggered, its action settings (e.g how to infract the user) are combined with the action settings of
    other triggered filters in the same event, and action is taken according to the combined action settings.
    """

    entry_type = ActionEntry

    def __init__(self, settings_data: dict, *, defaults: Settings | None = None, keep_empty: bool = False):
        super().__init__(settings_data, defaults=defaults, keep_empty=keep_empty)

    def union(self, other: Self) -> Self:
        """Combine the entries of two collections of settings into a new ActionsSettings."""
        actions = {}
        # A settings object doesn't necessarily have all types of entries (e.g in the case of filter overrides).
        for entry in self:
            if entry in other:
                actions[entry] = self[entry].union(other[entry])
            else:
                actions[entry] = self[entry]
        for entry in other:
            if entry not in actions:
                actions[entry] = other[entry]

        result = ActionSettings({})
        result.update(actions)
        return result

    async def action(self, ctx: FilterContext) -> None:
        """Execute the action of every action entry stored, as well as any additional actions in the context."""
        for entry in self.values():
            try:
                await entry.action(ctx)
            # Filtering should not stop even if one type of action raised an exception.
            # For example, if deleting the message raised somehow, it should still try to infract the user.
            except Exception:
                log.exception(traceback.format_exc())

        for action in ctx.additional_actions:
            try:
                await action(ctx)
            except Exception:
                log.exception(traceback.format_exc())

    def fallback_to(self, fallback: ActionSettings) -> ActionSettings:
        """Fill in missing entries from `fallback`."""
        new_actions = self.copy()
        for entry_name, entry_value in fallback.items():
            if entry_name not in self:
                new_actions[entry_name] = entry_value
        return new_actions


class Defaults(NamedTuple):
    """Represents an atomic list's default settings."""

    actions: ActionSettings
    validations: ValidationSettings

    def dict(self) -> dict[str, Any]:
        """Return a dict representation of the stored fields across all entries."""
        dict_ = {}
        for settings in self:
            dict_ = reduce(operator.or_, (entry.model_dump() for entry in settings.values()), dict_)
        return dict_
