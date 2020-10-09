import logging
import re

from discord import Colour, Message, NotFound
from discord.ext.commands import Cog

from bot.bot import Bot
from bot.constants import Channels, Colours, Event, Icons
from bot.exts.moderation.modlog import ModLog
from bot.utils.messages import format_user

WEBHOOK_URL_RE = re.compile(r"((?:https?://)?discord(?:app)?\.com/api/webhooks/\d+/)\S+/?", re.IGNORECASE)

ALERT_MESSAGE_TEMPLATE = (
    "{user}, looks like you posted a Discord webhook URL. Therefore, your "
    "message has been removed. Your webhook may have been **compromised** so "
    "please re-create the webhook **immediately**. If you believe this was "
    "mistake, please let us know."
)

log = logging.getLogger(__name__)


class WebhookRemover(Cog):
    """Scan messages to detect Discord webhooks links."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @property
    def mod_log(self) -> ModLog:
        """Get current instance of `ModLog`."""
        return self.bot.get_cog("ModLog")

    async def delete_and_respond(self, msg: Message, redacted_url: str) -> None:
        """Delete `msg` and send a warning that it contained the Discord webhook `redacted_url`."""
        # Don't log this, due internal delete, not by user. Will make different entry.
        self.mod_log.ignore(Event.message_delete, msg.id)

        try:
            await msg.delete()
        except NotFound:
            log.debug(f"Failed to remove webhook in message {msg.id}: message already deleted.")
            return

        await msg.channel.send(ALERT_MESSAGE_TEMPLATE.format(user=msg.author.mention))

        message = (
            f"{format_user(msg.author)} posted a Discord webhook URL to {msg.channel.mention}. "
            f"Webhook URL was `{redacted_url}`"
        )
        log.debug(message)

        # Send entry to moderation alerts.
        await self.mod_log.send_log_message(
            icon_url=Icons.token_removed,
            colour=Colour(Colours.soft_red),
            title="Discord webhook URL removed!",
            text=message,
            thumbnail=msg.author.avatar_url_as(static_format="png"),
            channel_id=Channels.mod_alerts
        )

        self.bot.stats.incr("tokens.removed_webhooks")

    @Cog.listener()
    async def on_message(self, msg: Message) -> None:
        """Check if a Discord webhook URL is in `message`."""
        # Ignore DMs; can't delete messages in there anyway.
        if not msg.guild or msg.author.bot:
            return

        matches = WEBHOOK_URL_RE.search(msg.content)
        if matches:
            await self.delete_and_respond(msg, matches[1] + "xxx")

    @Cog.listener()
    async def on_message_edit(self, before: Message, after: Message) -> None:
        """Check if a Discord webhook URL is in the edited message `after`."""
        await self.on_message(after)


def setup(bot: Bot) -> None:
    """Load `WebhookRemover` cog."""
    bot.add_cog(WebhookRemover(bot))
