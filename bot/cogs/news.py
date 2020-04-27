import logging
import typing as t
from datetime import date, datetime

import discord
import feedparser
from bs4 import BeautifulSoup
from dateutil import tz
from discord.ext.commands import Cog
from discord.ext.tasks import loop

from bot import constants
from bot.bot import Bot

PEPS_RSS_URL = "https://www.python.org/dev/peps/peps.rss/"

RECENT_THREADS_TEMPLATE = "https://mail.python.org/archives/list/{name}@python.org/recent-threads"
THREAD_TEMPLATE_URL = "https://mail.python.org/archives/api/list/{name}@python.org/thread/{id}/"
MAILMAN_PROFILE_URL = "https://mail.python.org/archives/users/{id}/"
THREAD_URL = "https://mail.python.org/archives/list/{list}@python.org/thread/{id}/"

AVATAR_URL = "https://www.python.org/static/opengraph-icon-200x200.png"

log = logging.getLogger(__name__)


class News(Cog):
    """Post new PEPs and Python News to `#python-news`."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.webhook_names = {}
        self.webhook: t.Optional[discord.Webhook] = None
        self.channel: t.Optional[discord.TextChannel] = None

        self.bot.loop.create_task(self.get_webhook_names())
        self.bot.loop.create_task(self.get_webhook_and_channel())

    async def start_tasks(self) -> None:
        """Start the tasks for fetching new PEPs and mailing list messages."""
        self.post_pep_news.start()
        self.post_maillist_news.start()

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

    async def get_webhook_names(self) -> None:
        """Get webhook author names from maillist API."""
        await self.bot.wait_until_guild_available()

        async with self.bot.http_session.get("https://mail.python.org/archives/api/lists") as resp:
            lists = await resp.json()

        for mail in lists:
            if mail["name"].split("@")[0] in constants.PythonNews.mail_lists:
                self.webhook_names[mail["name"].split("@")[0]] = mail["display_name"]

    @loop(minutes=20)
    async def post_pep_news(self) -> None:
        """Fetch new PEPs and when they don't have announcement in #python-news, create it."""
        # Wait until everything is ready and http_session available
        await self.bot.wait_until_guild_available()
        await self.sync_maillists()

        async with self.bot.http_session.get(PEPS_RSS_URL) as resp:
            data = feedparser.parse(await resp.text())

        news_listing = await self.bot.api_client.get("bot/bot-settings/news")
        payload = news_listing.copy()
        pep_news_ids = news_listing["data"]["pep"]
        pep_news = []

        for pep_id in pep_news_ids:
            message = discord.utils.get(self.bot.cached_messages, id=pep_id)
            if message is None:
                message = await self.channel.fetch_message(pep_id)
                if message is None:
                    log.warning("Can't fetch PEP new message ID.")
                    continue
            pep_news.append(message.embeds[0].title)

        # Reverse entries to send oldest first
        data["entries"].reverse()
        for new in data["entries"]:
            try:
                new_datetime = datetime.strptime(new["published"], "%a, %d %b %Y %X %Z")
            except ValueError:
                log.warning(f"Wrong datetime format passed in PEP new: {new['published']}")
                continue
            if (
                    new["title"] in pep_news
                    or new_datetime.date() < date.today()
            ):
                continue

            msg = await self.send_webhook(
                title=new["title"],
                description=new["summary"],
                timestamp=new_datetime,
                url=new["link"],
                webhook_profile_name=data["feed"]["title"],
                footer=data["feed"]["title"]
            )
            payload["data"]["pep"].append(msg.id)

            if msg.channel.type is discord.ChannelType.news:
                log.trace("Publishing PEP annnouncement because it was in a news channel")
                await msg.publish()

        # Apply new sent news to DB to avoid duplicate sending
        await self.bot.api_client.put("bot/bot-settings/news", json=payload)

    @loop(minutes=20)
    async def post_maillist_news(self) -> None:
        """Send new maillist threads to #python-news that is listed in configuration."""
        await self.bot.wait_until_guild_available()
        await self.sync_maillists()
        existing_news = await self.bot.api_client.get("bot/bot-settings/news")
        payload = existing_news.copy()

        for maillist in constants.PythonNews.mail_lists:
            async with self.bot.http_session.get(RECENT_THREADS_TEMPLATE.format(name=maillist)) as resp:
                recents = BeautifulSoup(await resp.text(), features="lxml")

            for thread in recents.html.body.div.find_all("a", href=True):
                # We want only these threads that have identifiers
                if "latest" in thread["href"]:
                    continue

                thread_information, email_information = await self.get_thread_and_first_mail(
                    maillist, thread["href"].split("/")[-2]
                )

                try:
                    new_date = datetime.strptime(email_information["date"], "%Y-%m-%dT%X%z")
                except ValueError:
                    log.warning(f"Invalid datetime from Thread email: {email_information['date']}")
                    continue

                if (
                        await self.check_new_exist(thread_information["subject"], new_date, maillist, existing_news)
                        or new_date.date() < date.today()
                ):
                    continue

                content = email_information["content"]
                link = THREAD_URL.format(id=thread["href"].split("/")[-2], list=maillist)
                msg = await self.send_webhook(
                    title=thread_information["subject"],
                    description=content[:500] + f"... [continue reading]({link})" if len(content) > 500 else content,
                    timestamp=new_date,
                    url=link,
                    author=f"{email_information['sender_name']} ({email_information['sender']['address']})",
                    author_url=MAILMAN_PROFILE_URL.format(id=email_information["sender"]["mailman_id"]),
                    webhook_profile_name=self.webhook_names[maillist],
                    footer=f"Posted to {self.webhook_names[maillist]}"
                )
                payload["data"][maillist].append(msg.id)

                if msg.channel.type is discord.ChannelType.news:
                    log.trace("Publishing PEP annnouncement because it was in a news channel")
                    await msg.publish()

        await self.bot.api_client.put("bot/bot-settings/news", json=payload)

    async def check_new_exist(self, title: str, timestamp: datetime, maillist: str, news: t.Dict[str, t.Any]) -> bool:
        """Check does this new title + timestamp already exist in #python-news."""
        for new in news["data"][maillist]:
            message = discord.utils.get(self.bot.cached_messages, id=new)
            if message is None:
                message = await self.channel.fetch_message(new)
                if message is None:
                    log.trace(f"Could not find message for {new} on mailing list {maillist}")
                    return False

            embed_time = message.embeds[0].timestamp.replace(tzinfo=tz.gettz("UTC"))

            if (
                message.embeds[0].title == title
                and embed_time == timestamp.astimezone(tz.gettz("UTC"))
            ):
                log.trace(f"Found existing message for '{title}'")
                return True

        log.trace(f"Found no existing message for '{title}'")
        return False

    async def send_webhook(self,
                           title: str,
                           description: str,
                           timestamp: datetime,
                           url: str,
                           webhook_profile_name: str,
                           footer: str,
                           author: t.Optional[str] = None,
                           author_url: t.Optional[str] = None,
                           ) -> discord.Message:
        """Send webhook entry and return sent message."""
        embed = discord.Embed(
            title=title,
            description=description,
            timestamp=timestamp,
            url=url,
            colour=constants.Colours.soft_green
        )
        if author and author_url:
            embed.set_author(
                name=author,
                url=author_url
            )
        embed.set_footer(text=footer, icon_url=AVATAR_URL)

        # Wait until Webhook is available
        while not self.webhook:
            pass

        return await self.webhook.send(
            embed=embed,
            username=webhook_profile_name,
            avatar_url=AVATAR_URL,
            wait=True
        )

    async def get_thread_and_first_mail(self, maillist: str, thread_identifier: str) -> t.Tuple[t.Any, t.Any]:
        """Get mail thread and first mail from mail.python.org based on `maillist` and `thread_identifier`."""
        async with self.bot.http_session.get(
                THREAD_TEMPLATE_URL.format(name=maillist, id=thread_identifier)
        ) as resp:
            thread_information = await resp.json()

        async with self.bot.http_session.get(thread_information["starting_email"]) as resp:
            email_information = await resp.json()
        return thread_information, email_information

    async def get_webhook_and_channel(self) -> None:
        """Storage #python-news channel Webhook and `TextChannel` to `News.webhook` and `channel`."""
        await self.bot.wait_until_guild_available()
        self.webhook = await self.bot.fetch_webhook(constants.PythonNews.webhook)
        self.channel = await self.bot.fetch_channel(constants.PythonNews.channel)

        await self.start_tasks()


def setup(bot: Bot) -> None:
    """Add `News` cog."""
    bot.add_cog(News(bot))
