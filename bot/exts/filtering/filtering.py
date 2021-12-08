import operator
from collections import defaultdict
from functools import reduce
from typing import Optional

from discord import Embed, HTTPException, Message
from discord.ext.commands import Cog
from discord.utils import escape_markdown

from bot.bot import Bot
from bot.constants import Colours, Webhooks
from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filter_lists import FilterList, filter_list_types
from bot.exts.filtering._filters.filter import Filter
from bot.exts.filtering._settings import ActionSettings
from bot.log import get_logger
from bot.utils.messages import format_channel, format_user

log = get_logger(__name__)


class Filtering(Cog):
    """Filtering and alerting for content posted on the server."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.filter_lists: dict[str, FilterList] = {}
        self._subscriptions: defaultdict[Event, list[FilterList]] = defaultdict(list)
        self.webhook = None

    async def cog_load(self) -> None:
        """
        Fetch the filter data from the API, parse it, and load it to the appropriate data structures.

        Additionally, fetch the alerting webhook.
        """
        await self.bot.wait_until_guild_available()
        already_warned = set()

        raw_filter_lists = await self.bot.api_client.get("bot/filter/filter_lists")
        for raw_filter_list in raw_filter_lists:
            list_name = raw_filter_list["name"]
            if list_name not in self.filter_lists:
                if list_name not in filter_list_types:
                    if list_name not in already_warned:
                        log.warning(
                            f"A filter list named {list_name} was loaded from the database, but no matching class."
                        )
                        already_warned.add(list_name)
                    continue
                self.filter_lists[list_name] = filter_list_types[list_name](self)
            self.filter_lists[list_name].add_list(raw_filter_list)

        try:
            self.webhook = await self.bot.fetch_webhook(Webhooks.filters)
        except HTTPException:
            log.error(f"Failed to fetch incidents webhook with id `{Webhooks.incidents}`.")

    def subscribe(self, filter_list: FilterList, *events: Event) -> None:
        """
        Subscribe a filter list to the given events.

        The filter list is added to a list for each event. When the event is triggered, the filter context will be
        dispatched to the subscribed filter lists.

        While it's possible to just make each filter list check the context's event, these are only the events a filter
        list expects to receive from the filtering cog, there isn't an actual limitation on the kinds of events a filter
        list can handle as long as the filter context is built properly. If for whatever reason we want to invoke a
        filter list outside of the usual procedure with the filtering cog, it will be more problematic if the events are
        hard-coded into each filter list.
        """
        for event in events:
            if filter_list not in self._subscriptions[event]:
                self._subscriptions[event].append(filter_list)

    async def _resolve_action(
        self, ctx: FilterContext
    ) -> tuple[dict[FilterList, list[Filter]], Optional[ActionSettings]]:
        """Get the filters triggered per list, and resolve from them the action that needs to be taken for the event."""
        triggered = {}
        for filter_list in self._subscriptions[ctx.event]:
            triggered[filter_list] = filter_list.triggers_for(ctx)

        result_actions = None
        if triggered:
            result_actions = reduce(
                operator.or_, (filter_.actions for filters in triggered.values() for filter_ in filters)
            )

        return triggered, result_actions

    @Cog.listener()
    async def on_message(self, msg: Message) -> None:
        """Filter the contents of a sent message."""
        if msg.author.bot:
            return

        ctx = FilterContext(Event.MESSAGE, msg.author, msg.channel, msg.content, msg, msg.embeds)

        triggered, result_actions = await self._resolve_action(ctx)
        if result_actions:
            await result_actions.action(ctx)
            if ctx.send_alert:
                await self._send_alert(ctx, triggered)

    async def _send_alert(self, ctx: FilterContext, triggered_filters: dict[FilterList, list[Filter]]) -> None:
        """Build an alert message from the filter context, and send it via the alert webhook."""
        if not self.webhook:
            return

        name = f"{ctx.event.name.replace('_', ' ').title()} Filter"

        embed = Embed(color=Colours.soft_orange)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        triggered_by = f"**Triggered by:** {format_user(ctx.author)}"
        if ctx.channel.guild:
            triggered_in = f"**Triggered in:** {format_channel(ctx.channel)}"
        else:
            triggered_in = "**DM**"
        if len(triggered_filters) == 1 and len(list(triggered_filters.values())[0]) == 1:
            filter_list, (filter_,) = next(iter(triggered_filters.items()))
            filters = f"**{filter_list.name.title()} Filter:** #{filter_.id} (`{filter_.content}`)"
            if filter_.description:
                filters += f" - {filter_.description}"
        else:
            filters = []
            for filter_list, list_filters in triggered_filters.items():
                filters.append(
                    (f"**{filter_list.name.title()} Filters:** "
                     ", ".join(f"#{filter_.id} (`{filter_.content}`)" for filter_ in list_filters))
                )
            filters = "\n".join(filters)

        matches = "**Matches:** " + ", ".join(repr(match) for match in ctx.matches)
        actions = "**Actions Taken:** " + (", ".join(ctx.action_descriptions) if ctx.action_descriptions else "-")
        content = f"**[Original Content]({ctx.message.jump_url})**: {escape_markdown(ctx.content)}"

        embed_content = "\n".join(
            part for part in (triggered_by, triggered_in, filters, matches, actions, content) if part
        )
        if len(embed_content) > 4000:
            embed_content = embed_content[:4000] + " [...]"
        embed.description = embed_content

        await self.webhook.send(username=name, content=ctx.alert_content, embeds=[embed, *ctx.alert_embeds])


async def setup(bot: Bot) -> None:
    """Load the Filtering cog."""
    await bot.add_cog(Filtering(bot))
