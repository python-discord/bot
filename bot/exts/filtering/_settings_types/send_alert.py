from typing import Any

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings_types.settings_entry import ActionEntry


class SendAlert(ActionEntry):
    """A setting entry which tells whether to send an alert message."""

    name = "send_alert"

    def __init__(self, entry_data: Any):
        super().__init__(entry_data)
        self.send_alert: bool = entry_data

    async def action(self, ctx: FilterContext) -> None:
        """Add the stored pings to the alert message content."""
        ctx.send_alert = self.send_alert

    def __or__(self, other: ActionEntry):
        """Combines two actions of the same type. Each type of action is executed once per filter."""
        if not isinstance(other, SendAlert):
            return NotImplemented

        return SendAlert(self.send_alert or other.send_alert)

