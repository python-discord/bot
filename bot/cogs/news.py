import logging
from datetime import datetime

import discord
import feedparser
from discord.ext.commands import Cog
from discord.ext.tasks import loop

from bot import constants
from bot.bot import Bot

PEPS_RSS_URL = "https://www.python.org/dev/peps/peps.rss/"

log = logging.getLogger(__name__)


class News(Cog):
    """Post new PEPs and Python News to `#python-news`."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.bot.loop.create_task(self.sync_maillists())

        self.post_pep_news.start()

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

    @loop(minutes=20)
    async def post_pep_news(self) -> None:
        """Fetch new PEPs and when they don't have announcement in #python-news, create it."""
        # Wait until everything is ready and http_session available
        await self.bot.wait_until_guild_available()

        async with self.bot.http_session.get(PEPS_RSS_URL) as resp:
            data = feedparser.parse(await resp.text())

        news_channel = self.bot.get_channel(constants.PythonNews.channel)
        webhook = await self.bot.fetch_webhook(constants.PythonNews.webhook)

        news_listing = await self.bot.api_client.get("bot/bot-settings/news")
        payload = news_listing.copy()
        pep_news_ids = news_listing["data"]["pep"]
        pep_news = []

        for pep_id in pep_news_ids:
            message = discord.utils.get(self.bot.cached_messages, id=pep_id)
            if message is None:
                message = await news_channel.fetch_message(pep_id)
                if message is None:
                    log.warning(f"Can't fetch news message with ID {pep_id}. Deleting it entry from DB.")
                    payload["data"]["pep"].remove(pep_id)
            pep_news.append((message.embeds[0].title, message.embeds[0].timestamp))

        # Reverse entries to send oldest first
        data["entries"].reverse()
        for new in data["entries"]:
            try:
                new_datetime = datetime.strptime(new["published"], "%a, %d %b %Y %X %Z")
            except ValueError:
                log.warning(f"Wrong datetime format passed in PEP new: {new['published']}")
                continue
            if (
                any(pep_new[0] == new["title"] for pep_new in pep_news)
                and any(pep_new[1] == new_datetime for pep_new in pep_news)
            ):
                continue

            embed = discord.Embed(
                title=new["title"],
                description=new["summary"],
                timestamp=new_datetime,
                url=new["link"],
                colour=constants.Colours.soft_green
            )

            pep_msg = await webhook.send(
                embed=embed,
                username=data["feed"]["title"],
                avatar_url="https://www.python.org/static/opengraph-icon-200x200.png",
                wait=True
            )
            payload["data"]["pep"].append(pep_msg.id)

        # Apply new sent news to DB to avoid duplicate sending
        await self.bot.api_client.put("bot/bot-settings/news", json=payload)


def setup(bot: Bot) -> None:
    """Add `News` cog."""
    bot.add_cog(News(bot))
