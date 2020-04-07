import logging
from io import BytesIO
from typing import Callable, List, Optional, Tuple
from urllib import parse

import discord
from dateutil.relativedelta import relativedelta
from discord import Embed
from discord.ext import commands
from discord.ext.commands import BucketType, Cog, Context, check, group

from bot.bot import Bot
from bot.constants import Colours, STAFF_ROLES, Wolfram
from bot.pagination import ImagePaginator
from bot.utils.time import humanize_delta

log = logging.getLogger(__name__)

APPID = Wolfram.key
DEFAULT_OUTPUT_FORMAT = "JSON"
QUERY = "http://api.wolframalpha.com/v2/{request}?{data}"
WOLF_IMAGE = "https://www.symbols.com/gi.php?type=1&id=2886&i=1"

MAX_PODS = 20

# Allows for 10 wolfram calls pr user pr day
usercd = commands.CooldownMapping.from_cooldown(Wolfram.user_limit_day, 60 * 60 * 24, BucketType.user)

# Allows for max api requests / days in month per day for the entire guild (Temporary)
guildcd = commands.CooldownMapping.from_cooldown(Wolfram.guild_limit_day, 60 * 60 * 24, BucketType.guild)


async def send_embed(
        ctx: Context,
        message_txt: str,
        colour: int = Colours.soft_red,
        footer: str = None,
        img_url: str = None,
        f: discord.File = None
) -> None:
    """Generate & send a response embed with Wolfram as the author."""
    embed = Embed(colour=colour)
    embed.description = message_txt
    embed.set_author(name="Wolfram Alpha",
                     icon_url=WOLF_IMAGE,
                     url="https://www.wolframalpha.com/")
    if footer:
        embed.set_footer(text=footer)

    if img_url:
        embed.set_image(url=img_url)

    await ctx.send(embed=embed, file=f)


def custom_cooldown(*ignore: List[int]) -> Callable:
    """
    Implement per-user and per-guild cooldowns for requests to the Wolfram API.

    A list of roles may be provided to ignore the per-user cooldown
    """
    async def predicate(ctx: Context) -> bool:
        user_bucket = usercd.get_bucket(ctx.message)

        if all(role.id not in ignore for role in ctx.author.roles):
            user_rate = user_bucket.update_rate_limit()

            if user_rate:
                # Can't use api; cause: member limit
                delta = relativedelta(seconds=int(user_rate))
                cooldown = humanize_delta(delta)
                message = (
                    "You've used up your limit for Wolfram|Alpha requests.\n"
                    f"Cooldown: {cooldown}"
                )
                await send_embed(ctx, message)
                return False

        guild_bucket = guildcd.get_bucket(ctx.message)
        guild_rate = guild_bucket.update_rate_limit()

        # Repr has a token attribute to read requests left
        log.debug(guild_bucket)

        if guild_rate:
            # Can't use api; cause: guild limit
            message = (
                "The max limit of requests for the server has been reached for today.\n"
                f"Cooldown: {int(guild_rate)}"
            )
            await send_embed(ctx, message)
            return False

        return True
    return check(predicate)


async def get_pod_pages(ctx: Context, bot: Bot, query: str) -> Optional[List[Tuple]]:
    """Get the Wolfram API pod pages for the provided query."""
    async with ctx.channel.typing():
        url_str = parse.urlencode({
            "input": query,
            "appid": APPID,
            "output": DEFAULT_OUTPUT_FORMAT,
            "format": "image,plaintext"
        })
        request_url = QUERY.format(request="query", data=url_str)

        async with bot.http_session.get(request_url) as response:
            json = await response.json(content_type='text/plain')

        result = json["queryresult"]

        if result["error"]:
            # API key not set up correctly
            if result["error"]["msg"] == "Invalid appid":
                message = "Wolfram API key is invalid or missing."
                log.warning(
                    "API key seems to be missing, or invalid when "
                    f"processing a wolfram request: {url_str}, Response: {json}"
                )
                await send_embed(ctx, message)
                return

            message = "Something went wrong internally with your request, please notify staff!"
            log.warning(f"Something went wrong getting a response from wolfram: {url_str}, Response: {json}")
            await send_embed(ctx, message)
            return

        if not result["success"]:
            message = f"I couldn't find anything for {query}."
            await send_embed(ctx, message)
            return

        if not result["numpods"]:
            message = "Could not find any results."
            await send_embed(ctx, message)
            return

        pods = result["pods"]
        pages = []
        for pod in pods[:MAX_PODS]:
            subs = pod.get("subpods")

            for sub in subs:
                title = sub.get("title") or sub.get("plaintext") or sub.get("id", "")
                img = sub["img"]["src"]
                pages.append((title, img))
        return pages


class Wolfram(Cog):
    """Commands for interacting with the Wolfram|Alpha API."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @group(name="wolfram", aliases=("wolf", "wa"), invoke_without_command=True)
    @custom_cooldown(*STAFF_ROLES)
    async def wolfram_command(self, ctx: Context, *, query: str) -> None:
        """Requests all answers on a single image, sends an image of all related pods."""
        url_str = parse.urlencode({
            "i": query,
            "appid": APPID,
        })
        query = QUERY.format(request="simple", data=url_str)

        # Give feedback that the bot is working.
        async with ctx.channel.typing():
            async with self.bot.http_session.get(query) as response:
                status = response.status
                image_bytes = await response.read()

            f = discord.File(BytesIO(image_bytes), filename="image.png")
            image_url = "attachment://image.png"

            if status == 501:
                message = "Failed to get response"
                footer = ""
                color = Colours.soft_red
            elif status == 400:
                message = "No input found"
                footer = ""
                color = Colours.soft_red
            elif status == 403:
                message = "Wolfram API key is invalid or missing."
                footer = ""
                color = Colours.soft_red
            else:
                message = ""
                footer = "View original for a bigger picture."
                color = Colours.soft_orange

            # Sends a "blank" embed if no request is received, unsure how to fix
            await send_embed(ctx, message, color, footer=footer, img_url=image_url, f=f)

    @wolfram_command.command(name="page", aliases=("pa", "p"))
    @custom_cooldown(*STAFF_ROLES)
    async def wolfram_page_command(self, ctx: Context, *, query: str) -> None:
        """
        Requests a drawn image of given query.

        Keywords worth noting are, "like curve", "curve", "graph", "pokemon", etc.
        """
        pages = await get_pod_pages(ctx, self.bot, query)

        if not pages:
            return

        embed = Embed()
        embed.set_author(name="Wolfram Alpha",
                         icon_url=WOLF_IMAGE,
                         url="https://www.wolframalpha.com/")
        embed.colour = Colours.soft_orange

        await ImagePaginator.paginate(pages, ctx, embed)

    @wolfram_command.command(name="cut", aliases=("c",))
    @custom_cooldown(*STAFF_ROLES)
    async def wolfram_cut_command(self, ctx: Context, *, query: str) -> None:
        """
        Requests a drawn image of given query.

        Keywords worth noting are, "like curve", "curve", "graph", "pokemon", etc.
        """
        pages = await get_pod_pages(ctx, self.bot, query)

        if not pages:
            return

        if len(pages) >= 2:
            page = pages[1]
        else:
            page = pages[0]

        await send_embed(ctx, page[0], colour=Colours.soft_orange, img_url=page[1])

    @wolfram_command.command(name="short", aliases=("sh", "s"))
    @custom_cooldown(*STAFF_ROLES)
    async def wolfram_short_command(self, ctx: Context, *, query: str) -> None:
        """Requests an answer to a simple question."""
        url_str = parse.urlencode({
            "i": query,
            "appid": APPID,
        })
        query = QUERY.format(request="result", data=url_str)

        # Give feedback that the bot is working.
        async with ctx.channel.typing():
            async with self.bot.http_session.get(query) as response:
                status = response.status
                response_text = await response.text()

            if status == 501:
                message = "Failed to get response"
                color = Colours.soft_red
            elif status == 400:
                message = "No input found"
                color = Colours.soft_red
            elif response_text == "Error 1: Invalid appid":
                message = "Wolfram API key is invalid or missing."
                color = Colours.soft_red
            else:
                message = response_text
                color = Colours.soft_orange

            await send_embed(ctx, message, color)


def setup(bot: Bot) -> None:
    """Load the Wolfram cog."""
    bot.add_cog(Wolfram(bot))
