import re
import typing as t
from datetime import UTC, datetime, timedelta

import discord
import feedparser
import sentry_sdk
from bs4 import BeautifulSoup
from discord.ext.commands import Cog
from discord.ext.tasks import loop
from pydis_core.site_api import ResponseCodeError

from bot import constants
from bot.bot import Bot
from bot.log import get_logger
from bot.utils.webhooks import send_webhook

PEPS_RSS_URL = "https://peps.python.org/peps.rss"

RECENT_THREADS_TEMPLATE = "https://mail.python.org/archives/list/{name}@python.org/recent-threads"
THREAD_TEMPLATE_URL = "https://mail.python.org/archives/api/list/{name}@python.org/thread/{id}/"
MAILMAN_PROFILE_URL = "https://mail.python.org/archives/users/{id}/"
THREAD_URL = "https://mail.python.org/archives/list/{list}@python.org/thread/{id}/"

AVATAR_URL = "https://www.python.org/static/opengraph-icon-200x200.png"

# By first matching everything within a codeblock,
# when matching markdown it won't be within a codeblock
MARKDOWN_REGEX = re.compile(
    r"(?P<codeblock>`.*?`)"  # matches everything within a codeblock
    r"|(?P<markdown>(?<!\\)[_|])",  # matches unescaped `_` and `|`
    re.DOTALL  # required to support multi-line codeblocks
)

log = get_logger(__name__)


class PythonNews(Cog):
    """Post new PEPs and Python News to `#python-news`."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.webhook_names = {}
        self.webhook: discord.Webhook | None = None
        self.seen_items: dict[str, set[str]] = {}

    async def cog_load(self) -> None:
        """Load all existing seen items from db and create any missing mailing lists."""
        with sentry_sdk.start_span(description="Fetch mailing lists from site"):
            response = await self.bot.api_client.get("bot/mailing-lists")

        for mailing_list in response:
            self.seen_items[mailing_list["name"]] = set(mailing_list["seen_items"])

        with sentry_sdk.start_span(description="Update site with new mailing lists"):
            for mailing_list in ("pep", *constants.PythonNews.mail_lists):
                if mailing_list not in self.seen_items:
                    await self.bot.api_client.post("bot/mailing-lists", json={"name": mailing_list})
                    self.seen_items[mailing_list] = set()

        self.fetch_new_media.start()

    async def cog_unload(self) -> None:
        """Stop news posting tasks on cog unload."""
        self.fetch_new_media.cancel()

    async def get_webhooks(self) -> None:
        """Get webhook author names from maillist API."""
        async with self.bot.http_session.get("https://mail.python.org/archives/api/lists") as resp:
            lists = await resp.json()

        for mail in lists:
            mailing_list_name = mail["name"].split("@")[0]
            if mailing_list_name in constants.PythonNews.mail_lists:
                self.webhook_names[mailing_list_name] = mail["display_name"]
        self.webhook = await self.bot.fetch_webhook(constants.PythonNews.webhook)

    @loop(minutes=20)
    async def fetch_new_media(self) -> None:
        """Fetch new mailing list messages and then new PEPs."""
        await self.bot.wait_until_guild_available()
        if not self.webhook:
            await self.get_webhooks()

        await self.post_maillist_news()
        await self.post_pep_news()

    @staticmethod
    def escape_markdown(content: str) -> str:
        """Escape the markdown underlines and spoilers that aren't in codeblocks."""
        return MARKDOWN_REGEX.sub(
            lambda match: match.group("codeblock") or "\\" + match.group("markdown"),
            content
        )

    async def post_pep_news(self) -> None:
        """Fetch new PEPs and when they don't have announcement in #python-news, create it."""
        async with self.bot.http_session.get(PEPS_RSS_URL) as resp:
            data = feedparser.parse(await resp.text("utf-8"))

        pep_numbers = self.seen_items["pep"]

        # Reverse entries to send oldest first
        data["entries"].reverse()
        for new in data["entries"]:
            try:
                # %Z doesn't actually set the tzinfo of the datetime object, manually set this to UTC
                pep_creation = datetime.strptime(new["published"], "%a, %d %b %Y %X %Z").replace(tzinfo=UTC)
            except ValueError:
                log.warning(f"Wrong datetime format passed in PEP new: {new['published']}")
                continue
            pep_nr = new["title"].split(":")[0].split()[1]
            if (
                    pep_nr in pep_numbers
                    # A PEP is assigned a creation date before it is reviewed and published to the RSS feed.
                    # The time between creation date and it appearing in the RSS feed is usually not long,
                    # but we allow up to 6 weeks to be safe.
                    or pep_creation < datetime.now(tz=UTC) - timedelta(weeks=6)
            ):
                continue

            # Build an embed and send a webhook
            embed = discord.Embed(
                title=self.escape_markdown(new["title"]),
                description=self.escape_markdown(new["summary"]),
                timestamp=pep_creation,
                url=new["link"],
                colour=constants.Colours.soft_green
            )
            embed.set_footer(text=data["feed"]["title"], icon_url=AVATAR_URL)
            msg = await send_webhook(
                webhook=self.webhook,
                username=data["feed"]["title"],
                embed=embed,
                avatar_url=AVATAR_URL,
                wait=True,
            )
            pep_successfully_added = await self.add_item_to_mail_list("pep", pep_nr)
            if pep_successfully_added and msg.channel.is_news():
                log.trace("Publishing PEP announcement because it was in a news channel")
                await msg.publish()

    async def post_maillist_news(self) -> None:
        """Send new maillist threads to #python-news that is listed in configuration."""
        for maillist in constants.PythonNews.mail_lists:
            if maillist not in self.seen_items:
                # If for some reason we have a mailing list that isn't tracked.
                log.warning("Mailing list %s doesn't exist in the database", maillist)
                continue

            async with self.bot.http_session.get(RECENT_THREADS_TEMPLATE.format(name=maillist)) as resp:
                recents = BeautifulSoup(await resp.text(), features="lxml")

            # When a <p> element is present in the response then the mailing list
            # has not had any activity during the current month, so therefore it
            # can be ignored.
            if recents.p:
                continue

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

                thread_id = thread_information["thread_id"]
                if (
                        thread_id in self.seen_items[maillist]
                        or "Re: " in thread_information["subject"]
                        or new_date.date() < datetime.now(tz=UTC).date()
                ):
                    continue

                content = self.escape_markdown(email_information["content"])
                link = THREAD_URL.format(id=thread["href"].split("/")[-2], list=maillist)

                # Build an embed and send a message to the webhook
                embed = discord.Embed(
                    title=self.escape_markdown(thread_information["subject"]),
                    description=content[:1000] + f"... [continue reading]({link})" if len(content) > 1000 else content,
                    timestamp=new_date,
                    url=link,
                    colour=constants.Colours.soft_green
                )
                embed.set_author(
                    name=f"{email_information['sender_name']} ({email_information['sender']['address']})",
                    url=MAILMAN_PROFILE_URL.format(id=email_information["sender"]["mailman_id"]),
                )
                embed.set_footer(
                    text=f"Posted to {self.webhook_names[maillist]}",
                    icon_url=AVATAR_URL,
                )
                msg = await send_webhook(
                    webhook=self.webhook,
                    username=self.webhook_names[maillist],
                    embed=embed,
                    avatar_url=AVATAR_URL,
                    wait=True,
                )
                thread_successfully_added = await self.add_item_to_mail_list(maillist, thread_id)
                if thread_successfully_added and msg.channel.is_news():
                    log.trace("Publishing mailing list message because it was in a news channel")
                    await msg.publish()

    async def add_item_to_mail_list(self, mail_list: str, item_identifier: str) -> bool:
        """Adds a new item to a particular mailing_list."""
        try:
            await self.bot.api_client.post(f"bot/mailing-lists/{mail_list}/seen-items", json=item_identifier)
            self.seen_items[mail_list].add(item_identifier)
            # Increase this specific mailing list counter in stats
            self.bot.stats.incr(f"python_news.posted.{mail_list.replace('-', '_')}")
            return True

        except ResponseCodeError as e:
            non_field_errors = e.response_json.get("non_field_errors", [])
            if non_field_errors != ["Seen item already known."]:
                raise e
            log.trace(
                "Item %s has already been seen in the following mailing list: %s",
                item_identifier,
                mail_list
            )
            return False

    async def get_thread_and_first_mail(self, maillist: str, thread_identifier: str) -> tuple[t.Any, t.Any]:
        """Get mail thread and first mail from mail.python.org based on `maillist` and `thread_identifier`."""
        async with self.bot.http_session.get(
                THREAD_TEMPLATE_URL.format(name=maillist, id=thread_identifier)
        ) as resp:
            thread_information = await resp.json()

        async with self.bot.http_session.get(thread_information["starting_email"]) as resp:
            email_information = await resp.json()
        return thread_information, email_information


async def setup(bot: Bot) -> None:
    """Add `News` cog."""
    await bot.add_cog(PythonNews(bot))
