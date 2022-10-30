from collections import defaultdict
from typing import ClassVar

from botcore.utils import scheduling
from discord import Message
from discord.errors import HTTPException

from bot.constants import Channels
from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._settings_types.settings_entry import ActionEntry
from bot.utils.messages import send_attachments


async def upload_messages_attachments(ctx: FilterContext, messages: list[Message]) -> None:
    """Re-upload the messages' attachments for future logging."""
    if not messages:
        return
    destination = messages[0].guild.get_channel(Channels.attachment_log)
    for message in messages:
        if message.attachments and message.id not in ctx.attachments:
            ctx.attachments[message.id] = await send_attachments(message, destination, link_large=False)


class DeleteMessages(ActionEntry):
    """A setting entry which tells whether to delete the offending message(s)."""

    name: ClassVar[str] = "delete_messages"
    description: ClassVar[str] = (
        "A boolean field. If True, the filter being triggered will cause the offending message to be deleted."
    )

    delete_messages: bool

    async def action(self, ctx: FilterContext) -> None:
        """Delete the context message(s)."""
        if not self.delete_messages or not ctx.message:
            return

        if not ctx.message.guild:
            return

        channel_messages = defaultdict(set)  # Duplicates will cause batch deletion to fail.
        for message in {ctx.message} | ctx.related_messages:
            channel_messages[message.channel].add(message)

        success = fail = 0
        deleted = list()
        for channel, messages in channel_messages.items():
            try:
                await channel.delete_messages(messages)
            except HTTPException:
                fail += len(messages)
            else:
                success += len(messages)
                deleted.extend(messages)
        scheduling.create_task(upload_messages_attachments(ctx, deleted))

        if not fail:
            if success == 1:
                ctx.action_descriptions.append("deleted")
            else:
                ctx.action_descriptions.append("deleted all")
        elif not success:
            if fail == 1:
                ctx.action_descriptions.append("failed to delete")
            else:
                ctx.action_descriptions.append("all failed to delete")
        else:
            ctx.action_descriptions.append(f"{success} deleted, {fail} failed to delete")

    def __or__(self, other: ActionEntry):
        """Combines two actions of the same type. Each type of action is executed once per filter."""
        if not isinstance(other, DeleteMessages):
            return NotImplemented

        return DeleteMessages(delete_messages=self.delete_messages or other.delete_messages)
