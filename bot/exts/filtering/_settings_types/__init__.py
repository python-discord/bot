from os.path import dirname

from bot.exts.filtering._settings_types.settings_entry import ActionEntry, ValidationEntry
from bot.exts.filtering._utils import subclasses_in_package

action_types = subclasses_in_package(dirname(__file__), f"{__name__}.", ActionEntry)
validation_types = subclasses_in_package(dirname(__file__), f"{__name__}.", ValidationEntry)

settings_types = {
    "ActionEntry": {settings_type.name: settings_type for settings_type in action_types},
    "ValidationEntry": {settings_type.name: settings_type for settings_type in validation_types}
}

__all__ = [settings_types]
