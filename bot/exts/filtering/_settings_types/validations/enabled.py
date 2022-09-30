from typing import ClassVar

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings_types.settings_entry import ValidationEntry


class Enabled(ValidationEntry):
    """A setting entry which tells whether the filter is enabled."""

    name: ClassVar[str] = "enabled"
    description: ClassVar[str] = (
        "A boolean field. Setting it to False allows disabling the filter without deleting it entirely."
    )

    enabled: bool

    def triggers_on(self, ctx: FilterContext) -> bool:
        """Return whether the filter is enabled."""
        return self.enabled
