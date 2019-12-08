import asyncio
import logging
import random
import textwrap
from datetime import datetime, timedelta
from typing import List

from discord import Colour, Embed, TextChannel
from discord.ext.commands import Cog, Context, group
from discord.ext.tasks import loop

from bot.bot import Bot
from bot.constants import Channels, ERROR_REPLIES, Emojis, Reddit as RedditConfig, STAFF_ROLES, Webhooks
from bot.converters import Subreddit
from bot.decorators import with_role
from bot.pagination import LinePaginator

log = logging.getLogger(__name__)


class Reddit(Cog):
    """Track subreddit posts and show detailed statistics about them."""

    HEADERS = {"User-Agent": "Discord Bot: PythonDiscord (https://pythondiscord.com/)"}
    URL = "https://www.reddit.com"
    MAX_FETCH_RETRIES = 3

    def __init__(self, bot: Bot):
        self.bot = bot

        self.webhook = None  # set in on_ready
        bot.loop.create_task(self.init_reddit_ready())

        self.auto_poster_loop.start()

    def cog_unload(self) -> None:
        """Stops the loops when the cog is unloaded."""
        self.auto_poster_loop.cancel()

    async def init_reddit_ready(self) -> None:
        """Sets the reddit webhook when the cog is loaded."""
        await self.bot.wait_until_ready()
        if not self.webhook:
            self.webhook = await self.bot.fetch_webhook(Webhooks.reddit)

    @property
    def channel(self) -> TextChannel:
        """Get the #reddit channel object from the bot's cache."""
        return self.bot.get_channel(Channels.reddit)

    async def fetch_posts(self, route: str, *, amount: int = 25, params: dict = None) -> List[dict]:
        """A helper method to fetch a certain amount of Reddit posts at a given route."""
        # Reddit's JSON responses only provide 25 posts at most.
        if not 25 >= amount > 0:
            raise ValueError("Invalid amount of subreddit posts requested.")

        if params is None:
            params = {}

        url = f"{self.URL}/{route}.json"
        for _ in range(self.MAX_FETCH_RETRIES):
            response = await self.bot.http_session.get(
                url=url,
                headers=self.HEADERS,
                params=params
            )
            if response.status == 200 and response.content_type == 'application/json':
                # Got appropriate response - process and return.
                content = await response.json()
                posts = content["data"]["children"]
                return posts[:amount]

            await asyncio.sleep(3)

        log.debug(f"Invalid response from: {url} - status code {response.status}, mimetype {response.content_type}")
        return list()  # Failed to get appropriate response within allowed number of retries.

    async def get_top_posts(self, subreddit: Subreddit, time: str = "all", amount: int = 5) -> Embed:
        """
        Get the top amount of posts for a given subreddit within a specified timeframe.

        A time of "all" will get posts from all time, "day" will get top daily posts and "week" will get the top
        weekly posts.

        The amount should be between 0 and 25 as Reddit's JSON requests only provide 25 posts at most.
        """
        embed = Embed(description="")

        posts = await self.fetch_posts(
            route=f"{subreddit}/top",
            amount=amount,
            params={"t": time}
        )

        if not posts:
            embed.title = random.choice(ERROR_REPLIES)
            embed.colour = Colour.red()
            embed.description = (
                "Sorry! We couldn't find any posts from that subreddit. "
                "If this problem persists, please let us know."
            )

            return embed

        for post in posts:
            data = post["data"]

            text = data["selftext"]
            if text:
                text = textwrap.shorten(text, width=128, placeholder="...")
                text += "\n"  # Add newline to separate embed info

            ups = data["ups"]
            comments = data["num_comments"]
            author = data["author"]

            title = textwrap.shorten(data["title"], width=64, placeholder="...")
            link = self.URL + data["permalink"]

            embed.description += (
                f"**[{title}]({link})**\n"
                f"{text}"
                f"{Emojis.upvotes} {ups} {Emojis.comments} {comments} {Emojis.user} {author}\n\n"
            )

        embed.colour = Colour.blurple()
        return embed

    @loop()
    async def auto_poster_loop(self) -> None:
        """Post the top 5 posts daily, and the top 5 posts weekly."""
        # once we upgrade to d.py 1.3 this can be removed and the loop can use the `time=datetime.time.min` parameter
        now = datetime.utcnow()
        tomorrow = now + timedelta(days=1)
        midnight_tomorrow = tomorrow.replace(hour=0, minute=0, second=0)
        seconds_until = (midnight_tomorrow - now).total_seconds()

        await asyncio.sleep(seconds_until)

        await self.bot.wait_until_ready()
        if not self.webhook:
            await self.bot.fetch_webhook(Webhooks.reddit)

        if datetime.utcnow().weekday() == 0:
            await self.top_weekly_posts()
            # if it's a monday send the top weekly posts

        for subreddit in RedditConfig.subreddits:
            top_posts = await self.get_top_posts(subreddit=subreddit, time="day")
            await self.webhook.send(username=f"{subreddit} Top Daily Posts", embed=top_posts)

    async def top_weekly_posts(self) -> None:
        """Post a summary of the top posts."""
        for subreddit in RedditConfig.subreddits:
            # Send and pin the new weekly posts.
            top_posts = await self.get_top_posts(subreddit=subreddit, time="week")

            message = await self.webhook.send(wait=True, username=f"{subreddit} Top Weekly Posts", embed=top_posts)

            if subreddit.lower() == "r/python":
                if not self.channel:
                    log.warning("Failed to get #reddit channel to remove pins in the weekly loop.")
                    return

                # Remove the oldest pins so that only 12 remain at most.
                pins = await self.channel.pins()

                while len(pins) >= 12:
                    await pins[-1].unpin()
                    del pins[-1]

                await message.pin()

    @group(name="reddit", invoke_without_command=True)
    async def reddit_group(self, ctx: Context) -> None:
        """View the top posts from various subreddits."""
        await ctx.invoke(self.bot.get_command("help"), "reddit")

    @reddit_group.command(name="top")
    async def top_command(self, ctx: Context, subreddit: Subreddit = "r/Python") -> None:
        """Send the top posts of all time from a given subreddit."""
        async with ctx.typing():
            embed = await self.get_top_posts(subreddit=subreddit, time="all")

        await ctx.send(content=f"Here are the top {subreddit} posts of all time!", embed=embed)

    @reddit_group.command(name="daily")
    async def daily_command(self, ctx: Context, subreddit: Subreddit = "r/Python") -> None:
        """Send the top posts of today from a given subreddit."""
        async with ctx.typing():
            embed = await self.get_top_posts(subreddit=subreddit, time="day")

        await ctx.send(content=f"Here are today's top {subreddit} posts!", embed=embed)

    @reddit_group.command(name="weekly")
    async def weekly_command(self, ctx: Context, subreddit: Subreddit = "r/Python") -> None:
        """Send the top posts of this week from a given subreddit."""
        async with ctx.typing():
            embed = await self.get_top_posts(subreddit=subreddit, time="week")

        await ctx.send(content=f"Here are this week's top {subreddit} posts!", embed=embed)

    @with_role(*STAFF_ROLES)
    @reddit_group.command(name="subreddits", aliases=("subs",))
    async def subreddits_command(self, ctx: Context) -> None:
        """Send a paginated embed of all the subreddits we're relaying."""
        embed = Embed()
        embed.title = "Relayed subreddits."
        embed.colour = Colour.blurple()

        await LinePaginator.paginate(
            RedditConfig.subreddits,
            ctx, embed,
            footer_text="Use the reddit commands along with these to view their posts.",
            empty=False,
            max_lines=15
        )


def setup(bot: Bot) -> None:
    """Reddit cog load."""
    bot.add_cog(Reddit(bot))
    log.info("Cog loaded: Reddit")
