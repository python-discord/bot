import re

from pydis_core.utils.logging import get_logger

from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filters.filter import UniqueFilter
from bot.utils.helpers import remove_subdomain_from_url

log = get_logger(__name__)

URL_RE = re.compile(r"(https?://\S+)", flags=re.IGNORECASE)


class RichEmbedFilter(UniqueFilter):
    """Filter messages which contain rich embeds not auto-generated from a URL."""

    name = "rich_embed"
    events = (Event.MESSAGE, Event.MESSAGE_EDIT)

    async def triggered_on(self, ctx: FilterContext) -> bool:
        """Determine if `msg` contains any rich embeds not auto-generated from a URL."""
        if ctx.embeds:
            if ctx.event == Event.MESSAGE_EDIT:
                if not ctx.message.edited_at:  # This might happen, apparently.
                    return False
                # If the edit delta is less than 100 microseconds, it's probably a double filter trigger.
                delta = ctx.message.edited_at - (ctx.before_message.edited_at or ctx.before_message.created_at)
                if delta.total_seconds() < 0.0001:
                    return False

            for embed in ctx.embeds:
                if embed.type == "rich":
                    urls = URL_RE.findall(ctx.content)
                    final_urls = set(urls)
                    # This is due to the way discord renders relative urls in Embeds
                    # if the following url is sent: https://mobile.twitter.com/something
                    # Discord renders it as https://twitter.com/something
                    for url in urls:
                        final_urls.add(remove_subdomain_from_url(url))
                    if not embed.url or embed.url not in final_urls:
                        # If `embed.url` does not exist or if `embed.url` is not part of the content
                        # of the message, it's unlikely to be an auto-generated embed by Discord.
                        ctx.alert_embeds.extend(ctx.embeds)
                        return True

                    log.trace(
                        "Found a rich embed sent by a regular user account, "
                        "but it was likely just an automatic URL embed."
                    )

        return False
