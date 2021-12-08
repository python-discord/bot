from contextlib import suppress
from typing import Any

from discord.errors import NotFound

from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._settings_types.settings_entry import ActionEntry


class DeleteMessages(ActionEntry):
    """A setting entry which tells whether to delete the offending message(s)."""

    name = "delete_messages"

    def __init__(self, entry_data: Any):
        super().__init__(entry_data)
        self.delete: bool = entry_data

    async def action(self, ctx: FilterContext) -> None:
        """Delete the context message(s)."""
        if not self.delete or ctx.event not in (Event.MESSAGE, Event.MESSAGE_EDIT):
            return

        with suppress(NotFound):
            if ctx.message.guild:
                await ctx.message.delete()
        ctx.action_descriptions.append("deleted")

    def __or__(self, other: ActionEntry):
        """Combines two actions of the same type. Each type of action is executed once per filter."""
        if not isinstance(other, DeleteMessages):
            return NotImplemented

        return DeleteMessages(self.delete or other.delete)

