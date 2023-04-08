from typing import ClassVar

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings_types.settings_entry import ValidationEntry


class FilterDM(ValidationEntry):
    """A setting entry which tells whether to apply the filter to DMs."""

    name: ClassVar[str] = "filter_dm"
    description: ClassVar[str] = "A boolean field. If True, the filter can trigger for messages sent to the bot in DMs."

    filter_dm: bool

    def triggers_on(self, ctx: FilterContext) -> bool:
        """Return whether the filter should be triggered even if it was triggered in DMs."""
        if not ctx.channel:  # No channel - out of scope for this setting.
            return True

        return ctx.channel.guild is not None or self.filter_dm
