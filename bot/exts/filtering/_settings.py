from __future__ import annotations
from abc import abstractmethod
from typing import Iterator, Mapping, Optional

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings_types import settings_types
from bot.exts.filtering._settings_types.settings_entry import ActionEntry, ValidationEntry
from bot.exts.filtering._utils import FieldRequiring
from bot.log import get_logger

log = get_logger(__name__)

_already_warned: set[str] = set()


def create_settings(settings_data: dict) -> tuple[Optional[ActionSettings], Optional[ValidationSettings]]:
    """
    Create and return instances of the Settings subclasses from the given data

    Additionally, warn for data entries with no matching class.
    """
    action_data = {}
    validation_data = {}
    for entry_name, entry_data in settings_data.items():
        if entry_name in settings_types["ActionEntry"]:
            action_data[entry_name] = entry_data
        elif entry_name in settings_types["ValidationEntry"]:
            validation_data[entry_name] = entry_data
        else:
            log.warning(
                f"A setting named {entry_name} was loaded from the database, but no matching class."
            )
            _already_warned.add(entry_name)
    return ActionSettings.create(action_data), ValidationSettings.create(validation_data)


class Settings(FieldRequiring):
    """
    A collection of settings.

    For processing the settings parts in the database and evaluating them on given contexts.

    Each filter list and filter has its own settings.

    A filter doesn't have to have its own settings. For every undefined setting, it falls back to the value defined in
    the filter list which contains the filter.
    """

    entry_type = FieldRequiring.MUST_SET

    _already_warned: set[str] = set()

    @abstractmethod
    def __init__(self, settings_data: dict):
        self._entries: dict[str, Settings.entry_type] = {}

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
                    new_entry = entry_cls.create(entry_data)
                    if new_entry:
                        self._entries[entry_name] = new_entry
                except TypeError as e:
                    raise TypeError(
                        f"Attempted to load a {entry_name} setting, but the response is malformed: {entry_data}"
                    ) from e

    def __contains__(self, item) -> bool:
        return item in self._entries

    def __setitem__(self, key: str, value: entry_type) -> None:
        self._entries[key] = value

    def copy(self):
        copy = self.__class__({})
        copy._entries = self._entries
        return copy

    def items(self) -> Iterator[tuple[str, entry_type]]:
        yield from self._entries.items()

    def update(self, mapping: Mapping[str, entry_type], **kwargs: entry_type) -> None:
        self._entries.update(mapping, **kwargs)

    @classmethod
    def create(cls, settings_data: dict) -> Optional[Settings]:
        """
        Returns a Settings object from `settings_data` if it holds any value, None otherwise.

        Use this method to create Settings objects instead of the init.
        The None value is significant for how a filter list iterates over its filters.
        """
        settings = cls(settings_data)
        # If an entry doesn't hold any values, its `create` method will return None.
        # If all entries are None, then the settings object holds no values.
        if not any(settings._entries.values()):
            return None

        return settings


class ValidationSettings(Settings):
    """
    A collection of validation settings.

    A filter is triggered only if all of its validation settings (e.g whether to invoke in DM) approve
    (the check returns True).
    """

    entry_type = ValidationEntry

    def __init__(self, settings_data: dict):
        super().__init__(settings_data)

    def evaluate(self, ctx: FilterContext) -> tuple[set[str], set[str]]:
        """Evaluates for each setting whether the context is relevant to the filter."""
        passed = set()
        failed = set()

        self._entries: dict[str, ValidationEntry]
        for name, validation in self._entries.items():
            if validation:
                if validation.triggers_on(ctx):
                    passed.add(name)
                else:
                    failed.add(name)

        return passed, failed


class ActionSettings(Settings):
    """
    A collection of action settings.

    If a filter is triggered, its action settings (e.g how to infract the user) are combined with the action settings of
    other triggered filters in the same event, and action is taken according to the combined action settings.
    """

    entry_type = ActionEntry

    def __init__(self, settings_data: dict):
        super().__init__(settings_data)

    def __or__(self, other: ActionSettings) -> ActionSettings:
        """Combine the entries of two collections of settings into a new ActionsSettings"""
        actions = {}
        # A settings object doesn't necessarily have all types of entries (e.g in the case of filter overrides).
        for entry in self._entries:
            if entry in other._entries:
                actions[entry] = self._entries[entry] | other._entries[entry]
            else:
                actions[entry] = self._entries[entry]
        for entry in other._entries:
            if entry not in actions:
                actions[entry] = other._entries[entry]

        result = ActionSettings({})
        result.update(actions)
        return result

    async def action(self, ctx: FilterContext) -> None:
        """Execute the action of every action entry stored."""
        for entry in self._entries.values():
            await entry.action(ctx)

    def fallback_to(self, fallback: ActionSettings) -> None:
        """Fill in missing entries from `fallback`."""
        for entry_name, entry_value in fallback.items():
            if entry_name not in self._entries:
                self._entries[entry_name] = entry_value
