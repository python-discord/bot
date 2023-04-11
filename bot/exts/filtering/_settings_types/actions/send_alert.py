from typing import ClassVar, Self

from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings_types.settings_entry import ActionEntry


class SendAlert(ActionEntry):
    """A setting entry which tells whether to send an alert message."""

    name: ClassVar[str] = "send_alert"
    description: ClassVar[str] = "A boolean. If all filters triggered set this to False, no mod-alert will be created."

    send_alert: bool

    async def action(self, ctx: FilterContext) -> None:
        """Add the stored pings to the alert message content."""
        ctx.send_alert = self.send_alert

    def union(self, other: Self) -> Self:
        """Combines two actions of the same type. Each type of action is executed once per filter."""
        return SendAlert(send_alert=self.send_alert or other.send_alert)
