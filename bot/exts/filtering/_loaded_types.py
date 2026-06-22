from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.exts.filtering._filters.filter import Filter
    from bot.exts.filtering._settings_types.settings_entry import SettingsEntry


@dataclass
class LoadedTypes:
    """Container for loaded type metadata used across the filtering UI."""

    filters: dict[str, type["Filter"]]
    settings: dict[str, tuple[str, "SettingsEntry", type]]
    filter_settings: dict[str, dict[str, tuple[str, "SettingsEntry", type]]]
