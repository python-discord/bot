import logging
import re

from discord import Colour, Message
from discord.ext.commands import Cog

from bot.bot import Bot
from bot.cogs.moderation.modlog import ModLog
from bot.constants import Channels, Colours, Event, Icons

WEBHOOK_URL_RE = re.compile(r"discordapp\.com/api/webhooks/\d+/\S+/?")

ALERT_MESSAGE_TEMPLATE = (
    "{user}, looks like you posted Discord Webhook URL to chat. "
    "I removed this, but we **strongly** suggest to change this now "
    "to prevent any spam abuse to channel. Please avoid doing this in future. "
    "If you believe this was mistake, please let us know."
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

    async def scan_message(self, msg: Message) -> bool:
        """Scan message content to detect Webhook URLs. Return `bool` about does this have Discord webhook URL."""
        matches = WEBHOOK_URL_RE.search(msg.content)
        if matches:
            return True
        else:
            return False

    async def delete_and_respond(self, msg: Message, url: str) -> None:
        """Delete message and show warning when message contains Discord Webhook URL."""
        # Create URL that will be sent to logs, remove token
        parts = url.split("/")
        parts[-1] = "xxx"
        url = "/".join(parts)

        # Don't log this, due internal delete, not by user. Will make different entry.
        self.mod_log.ignore(Event.message_delete, msg.id)
        await msg.delete()
        await msg.channel.send(ALERT_MESSAGE_TEMPLATE.format(user=msg.author.mention))

        message = (
            f"{msg.author} ({msg.author.id}) posted Discord Webhook URL "
            f"to {msg.channel}. Webhook URL was {url}"
        )
        log.debug(message)

        # Send entry to moderation alerts.
        await self.mod_log.send_log_message(
            icon_url=Icons.token_removed,
            colour=Colour(Colours.soft_red),
            title="Discord Webhook URL removed!",
            text=message,
            thumbnail=msg.author.avatar_url_as(static_format="png"),
            channel_id=Channels.mod_alerts
        )


def setup(bot: Bot) -> None:
    """Load `WebhookRemover` cog."""
    bot.add_cog(WebhookRemover(bot))
