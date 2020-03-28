import re

from discord import Message
from discord.ext.commands import Cog

from bot.bot import Bot
from bot.cogs.moderation.modlog import ModLog

WEBHOOK_URL_RE = re.compile(r"discordapp\.com/api/webhooks/\d+/\S+/?")


class WebhookRemover(Cog):
    """Scan messages to detect Discord webhooks links."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @property
    def mod_log(self) -> ModLog:
        """Get current instance of `ModLog`."""
        return self.bot.get_cog("ModLog")

    async def scan_message(self, msg: Message) -> bool:
        """Scan message content to detect Webhook URLs. Return `bool` about does this have webhook URL."""
        matches = WEBHOOK_URL_RE.search(msg.content)
        if matches:
            return True
        else:
            return False


def setup(bot: Bot) -> None:
    """Load `WebhookRemover` cog."""
    bot.add_cog(WebhookRemover(bot))
