from bot.exts.filtering._settings_types.actions import action_types
from bot.exts.filtering._settings_types.validations import validation_types

settings_types = {
    "ActionEntry": {settings_type.name: settings_type for settings_type in action_types},
    "ValidationEntry": {settings_type.name: settings_type for settings_type in validation_types}
}

__all__ = [settings_types]
