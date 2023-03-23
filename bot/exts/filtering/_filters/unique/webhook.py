import re
from collections.abc import Callable, Coroutine

from pydis_core.utils.logging import get_logger

import bot
from bot import constants
from bot.exts.filtering._filter_context import Event, FilterContext
from bot.exts.filtering._filters.filter import UniqueFilter
from bot.exts.moderation.modlog import ModLog

log = get_logger(__name__)


WEBHOOK_URL_RE = re.compile(
    r"((?:https?://)?(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/)\S+/?",
    re.IGNORECASE
)


class WebhookFilter(UniqueFilter):
    """Scan messages to detect Discord webhooks links."""

    name = "webhook"
    events = (Event.MESSAGE, Event.MESSAGE_EDIT, Event.SNEKBOX)

    @property
    def mod_log(self) -> ModLog | None:
        """Get current instance of `ModLog`."""
        return bot.instance.get_cog("ModLog")

    async def triggered_on(self, ctx: FilterContext) -> bool:
        """Search for a webhook in the given content. If found, attempt to delete it."""
        matches = set(WEBHOOK_URL_RE.finditer(ctx.content))
        if not matches:
            return False

        # Don't log this.
        if ctx.message and (mod_log := self.mod_log):
            mod_log.ignore(constants.Event.message_delete, ctx.message.id)

        for i, match in enumerate(matches, start=1):
            extra = "" if len(matches) == 1 else f" ({i})"
            # Queue the webhook for deletion.
            ctx.additional_actions.append(self._delete_webhook_wrapper(match[0], extra))
            # Don't show the full webhook in places such as the mod alert.
            ctx.content = ctx.content.replace(match[0], match[1] + "xxx")

        return True

    @staticmethod
    def _delete_webhook_wrapper(webhook_url: str, extra_message: str) -> Callable[[FilterContext], Coroutine]:
        """Create the action to perform when a webhook should be deleted."""
        async def _delete_webhook(ctx: FilterContext) -> None:
            """Delete the given webhook and update the filter context."""
            async with bot.instance.http_session.delete(webhook_url) as resp:
                # The Discord API Returns a 204 NO CONTENT response on success.
                if resp.status == 204:
                    ctx.action_descriptions.append("webhook deleted" + extra_message)
                else:
                    ctx.action_descriptions.append("failed to delete webhook" + extra_message)

        return _delete_webhook
