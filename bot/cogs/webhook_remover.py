from discord.ext.commands import Cog

from bot.bot import Bot


class WebhookRemover(Cog):
    """Scan messages to detect Discord webhooks links."""

    def __init__(self, bot: Bot):
        self.bot = bot


def setup(bot: Bot) -> None:
    """Load `WebhookRemover` cog."""
    bot.add_cog(WebhookRemover(bot))
