from collections import defaultdict
from typing import ClassVar, Self

from discord import Message, Thread
from discord.errors import HTTPException
from pydis_core.utils import scheduling
from pydis_core.utils.logging import get_logger

import bot
from bot.constants import Channels
from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._settings_types.settings_entry import ActionEntry
from bot.exts.filtering._utils import FakeContext
from bot.utils.messages import send_attachments

log = get_logger(__name__)

SUPERSTAR_REASON = (
    "Your nickname was found to be in violation of our code of conduct. "
    "If you believe this is a mistake, please let us know."
)


async def upload_messages_attachments(ctx: FilterContext, messages: list[Message]) -> None:
    """Re-upload the messages' attachments for future logging."""
    if not messages:
        return
    destination = messages[0].guild.get_channel(Channels.attachment_log)
    for message in messages:
        if message.attachments and message.id not in ctx.uploaded_attachments:
            ctx.uploaded_attachments[message.id] = await send_attachments(message, destination, link_large=False)


class RemoveContext(ActionEntry):
    """A setting entry which tells whether to delete the offending message(s)."""

    name: ClassVar[str] = "remove_context"
    description: ClassVar[str] = (
        "A boolean field. If True, the filter being triggered will cause the offending context to be removed. "
        "An offending message will be deleted, while an offending nickname will be superstarified."
    )

    remove_context: bool

    async def action(self, ctx: FilterContext) -> None:
        """Remove the offending context."""
        if not self.remove_context:
            return

        if ctx.event in (Event.MESSAGE, Event.MESSAGE_EDIT):
            await self._handle_messages(ctx)
        elif ctx.event == Event.NICKNAME:
            await self._handle_nickname(ctx)
        elif ctx.event == Event.THREAD_NAME:
            await self._handle_thread(ctx)

    @staticmethod
    async def _handle_messages(ctx: FilterContext) -> None:
        """Delete any messages involved in this context."""
        if not ctx.message or not ctx.message.guild:
            return

        # If deletion somehow fails at least this will allow scheduling for deletion.
        ctx.messages_deletion = True
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

    @staticmethod
    async def _handle_nickname(ctx: FilterContext) -> None:
        """Apply a superstar infraction to remove the user's nickname."""
        alerts_channel = bot.instance.get_channel(Channels.mod_alerts)
        if not alerts_channel:
            log.error(f"Unable to apply superstar as the context channel {alerts_channel} can't be found.")
            return
        command = bot.instance.get_command("superstar")
        if not command:
            user = ctx.author
            await alerts_channel.send(f":warning: Could not apply superstar to {user.mention}: command not found.")
            log.warning(f":warning: Could not apply superstar to {user.mention}: command not found.")
            ctx.action_descriptions.append("failed to superstar")
            return

        await command(FakeContext(ctx.message, alerts_channel, command), ctx.author, None, reason=SUPERSTAR_REASON)
        ctx.action_descriptions.append("superstarred")

    @staticmethod
    async def _handle_thread(ctx: FilterContext) -> None:
        """Delete the context thread."""
        if isinstance(ctx.channel, Thread):
            try:
                await ctx.channel.delete()
            except HTTPException:
                ctx.action_descriptions.append("failed to delete thread")
            else:
                ctx.action_descriptions.append("deleted thread")

    def union(self, other: Self) -> Self:
        """Combines two actions of the same type. Each type of action is executed once per filter."""
        return RemoveContext(remove_context=self.remove_context or other.remove_context)
