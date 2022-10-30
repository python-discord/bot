import asyncio
import typing
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import timedelta
from functools import reduce
from itertools import takewhile
from operator import add, or_

import arrow
from botcore.utils import scheduling
from botcore.utils.logging import get_logger
from discord import HTTPException, Member

import bot
from bot.constants import Webhooks
from bot.exts.filtering._filter_context import FilterContext
from bot.exts.filtering._filter_lists.filter_list import ListType, SubscribingAtomicList, UniquesListBase
from bot.exts.filtering._filters.antispam import antispam_filter_types
from bot.exts.filtering._filters.filter import UniqueFilter
from bot.exts.filtering._settings import ActionSettings
from bot.exts.filtering._settings_types.actions.infraction_and_notification import Infraction
from bot.exts.filtering._ui.ui import build_mod_alert

if typing.TYPE_CHECKING:
    from bot.exts.filtering.filtering import Filtering

log = get_logger(__name__)

ALERT_DELAY = 6


class AntispamList(UniquesListBase):
    """
    A list of anti-spam rules.

    Messages from the last X seconds is passed to each rule, which decide whether it triggers across those messages.
    """

    name = "antispam"

    def __init__(self, filtering_cog: 'Filtering'):
        super().__init__(filtering_cog)
        self.message_deletion_queue: dict[Member, DeletionContext] = dict()

    def get_filter_type(self, content: str) -> type[UniqueFilter] | None:
        """Get a subclass of filter matching the filter list and the filter's content."""
        try:
            return antispam_filter_types[content]
        except KeyError:
            if content not in self._already_warned:
                log.warn(f"An antispam filter named {content} was supplied, but no matching implementation found.")
                self._already_warned.add(content)
            return None

    async def actions_for(self, ctx: FilterContext) -> tuple[ActionSettings | None, list[str]]:
        """Dispatch the given event to the list's filters, and return actions to take and messages to relay to mods."""
        if not ctx.message:
            return None, []

        sublist: SubscribingAtomicList = self[ListType.DENY]
        potential_filters = [sublist.filters[id_] for id_ in sublist.subscriptions[ctx.event]]
        max_interval = max(filter_.extra_fields.interval for filter_ in potential_filters)

        earliest_relevant_at = arrow.utcnow() - timedelta(seconds=max_interval)
        relevant_messages = list(
            takewhile(lambda msg: msg.created_at > earliest_relevant_at, self.filtering_cog.message_cache)
        )
        new_ctx = ctx.replace(content=relevant_messages)
        triggers = sublist.filter_list_result(new_ctx)
        if not triggers:
            return None, []

        if ctx.author not in self.message_deletion_queue:
            self.message_deletion_queue[ctx.author] = DeletionContext()
            ctx.additional_actions.append(self._create_deletion_context_handler(ctx.author))
            ctx.related_channels |= {msg.channel for msg in ctx.related_messages}
        else:  # The additional messages found are already part of the deletion context
            ctx.related_messages = set()
        current_infraction = self.message_deletion_queue[ctx.author].current_infraction
        self.message_deletion_queue[ctx.author].add(ctx, triggers)

        current_actions = sublist.merge_actions(triggers) if triggers else None
        # Don't alert yet.
        current_actions.pop("ping", None)
        current_actions.pop("send_alert", None)
        new_infraction = current_actions["infraction_and_notification"].copy()
        # Smaller infraction value = higher in hierarchy.
        if not current_infraction or new_infraction.infraction_type.value < current_infraction.value:
            # Pick the first triggered filter for the reason, there's no good way to decide between them.
            new_infraction.infraction_reason = f"{triggers[0].name} spam - {ctx.filter_info[triggers[0]]}"
            current_actions["infraction_and_notification"] = new_infraction
            self.message_deletion_queue[ctx.author].current_infraction = new_infraction.infraction_type
        else:
            current_actions.pop("infraction_and_notification", None)

        # Provide some message in case another filter list wants there to be an alert.
        return current_actions, ["Handling spam event..."]

    def _create_deletion_context_handler(self, context_id: Member) -> Callable[[FilterContext], Coroutine]:
        async def schedule_processing(ctx: FilterContext) -> None:
            """
            Schedule a coroutine to process the deletion context.

            It cannot be awaited directly, as it waits ALERT_DELAY seconds, and actioning a filtering context depends on
            all actions finishing.

            This is async and takes a context to adhere to the type of ctx.additional_actions.
            """
            async def process_deletion_context() -> None:
                """Processes the Deletion Context queue."""
                log.trace("Sleeping before processing message deletion queue.")
                await asyncio.sleep(ALERT_DELAY)

                if context_id not in self.message_deletion_queue:
                    log.error(f"Started processing deletion queue for context `{context_id}`, but it was not found!")
                    return

                deletion_context = self.message_deletion_queue.pop(context_id)
                await deletion_context.send_alert(self)

            scheduling.create_task(process_deletion_context())

        return schedule_processing


@dataclass
class DeletionContext:
    """Represents a Deletion Context for a single spam event."""

    contexts: list[FilterContext] = field(default_factory=list)
    rules: set[UniqueFilter] = field(default_factory=set)
    current_infraction: Infraction | None = None

    def add(self, ctx: FilterContext, rules: list[UniqueFilter]) -> None:
        """Adds new rule violation events to the deletion context."""
        self.contexts.append(ctx)
        self.rules.update(rules)

    async def send_alert(self, antispam_list: AntispamList) -> None:
        """Post the mod alert."""
        if not self.contexts or not self.rules:
            return
        try:
            webhook = await bot.instance.fetch_webhook(Webhooks.filters)
        except HTTPException:
            return

        ctx, *other_contexts = self.contexts
        new_ctx = FilterContext(ctx.event, ctx.author, ctx.channel, ctx.content, ctx.message)
        new_ctx.action_descriptions = reduce(
            add, (other_ctx.action_descriptions for other_ctx in other_contexts), ctx.action_descriptions
        )
        # It shouldn't ever come to this, but just in case.
        if descriptions_num := len(new_ctx.action_descriptions) > 20:
            new_ctx.action_descriptions = new_ctx.action_descriptions[:20]
            new_ctx.action_descriptions[-1] += f" (+{descriptions_num - 20} other actions)"
        new_ctx.related_messages = reduce(
            or_, (other_ctx.related_messages for other_ctx in other_contexts), ctx.related_messages
        )
        new_ctx.related_channels = reduce(
            or_, (other_ctx.related_channels for other_ctx in other_contexts), ctx.related_channels
        )
        new_ctx.attachments = reduce(or_, (other_ctx.attachments for other_ctx in other_contexts), ctx.attachments)

        rules = list(self.rules)
        actions = antispam_list[ListType.DENY].merge_actions(rules)
        for action in list(actions):
            if action not in ("ping", "send_alert"):
                actions.pop(action, None)
        await actions.action(new_ctx)

        messages = antispam_list[ListType.DENY].format_messages(rules)
        embed = await build_mod_alert(new_ctx, {antispam_list: messages})
        if other_contexts:
            embed.set_footer(
                text="The list of actions taken includes actions from additional contexts after deletion began."
            )
        await webhook.send(username="Anti-Spam", content=ctx.alert_content, embeds=[embed])
