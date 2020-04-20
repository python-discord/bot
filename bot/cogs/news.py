import discord
from discord.ext.commands import Cog

from bot import constants
from bot.bot import Bot


class News(Cog):
    """Post new PEPs and Python News to `#python-news`."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.bot.loop.create_task(self.sync_maillists())
        self.webhook = self.bot.loop.create_task(self.get_webhook())

    async def sync_maillists(self) -> None:
        """Sync currently in-use maillists with API."""
        # Wait until guild is available to avoid running before everything is ready
        await self.bot.wait_until_guild_available()

        response = await self.bot.api_client.get("bot/bot-settings/news")
        for mail in constants.PythonNews.mail_lists:
            if mail not in response["data"]:
                response["data"][mail] = []

        # Because we are handling PEPs differently, we don't include it to mail lists
        if "pep" not in response["data"]:
            response["data"]["pep"] = []

        await self.bot.api_client.put("bot/bot-settings/news", json=response)

    async def get_webhook(self) -> discord.Webhook:
        """Get #python-news channel webhook."""
        return await self.bot.fetch_webhook(constants.PythonNews.webhook)


def setup(bot: Bot) -> None:
    """Add `News` cog."""
    bot.add_cog(News(bot))
