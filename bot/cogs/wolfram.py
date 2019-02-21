import logging
from io import BytesIO
from typing import List, Optional, Tuple
from urllib import parse

import discord
from discord import Embed
from discord.ext import commands
from discord.ext.commands import BucketType, Context, check, group

from bot.constants import Colours, STAFF_ROLES, Wolfram
from bot.pagination import ImagePaginator

log = logging.getLogger(__name__)

APPID = Wolfram.key
DEFAULT_OUTPUT_FORMAT = "JSON"
QUERY = "http://api.wolframalpha.com/v2/{request}?{data}"
WOLF_IMAGE = "https://www.symbols.com/gi.php?type=1&id=2886&i=1"

MAX_PODS = 20

# Allows for 10 wolfram calls pr user pr day
usercd = commands.CooldownMapping.from_cooldown(Wolfram.user_limit_day, 60*60*24, BucketType.user)

# Allows for max api requests / days in month per day for the entire guild (Temporary)
guildcd = commands.CooldownMapping.from_cooldown(Wolfram.guild_limit_day, 60*60*24, BucketType.guild)


async def send_embed(
        ctx: Context,
        message_txt: str,
        colour: int = Colours.soft_red,
        footer: str = None,
        img_url: str = None,
        f: discord.File = None
) -> None:
    """
    Generates an embed with wolfram as the author, with message_txt as description,
    adds custom colour if specified, a footer and image (could be a file with f param) and sends
    the embed through ctx
    :param ctx: Context
    :param message_txt: str - Message to be sent
    :param colour: int - Default: Colours.soft_red - Colour of embed
    :param footer: str - Default: None - Adds a footer to the embed
    :param img_url:str - Default: None - Adds an image to the embed
    :param f: discord.File - Default: None - Add a file to the msg, often attached as image to embed
    """

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


def custom_cooldown(*ignore: List[int]) -> check:
    """
    Custom cooldown mapping that applies a specific requests per day to users.
    Staff is ignored by the user cooldown, however the cooldown implements a
    total amount of uses per day for the entire guild. (Configurable in configs)

    :param ignore: List[int] -- list of ids of roles to be ignored by user cooldown
    :return: check
    """

    async def predicate(ctx: Context) -> bool:
        user_bucket = usercd.get_bucket(ctx.message)

        if ctx.author.top_role.id not in ignore:
            user_rate = user_bucket.update_rate_limit()

            if user_rate:
                # Can't use api; cause: member limit
                message = (
                    "You've used up your limit for Wolfram|Alpha requests.\n"
                    f"Cooldown: {int(user_rate)}"
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


async def get_pod_pages(ctx, bot, query: str) -> Optional[List[Tuple]]:
    # Give feedback that the bot is working.
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

        if not result["success"]:
            message = f"I couldn't find anything for {query}."
            await send_embed(ctx, message)
            return

        if result["error"]:
            message = "Something went wrong internally with your request, please notify staff!"
            log.warning(f"Something went wrong getting a response from wolfram: {url_str}, Response: {json}")
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


class Wolfram:
    """
    Commands for interacting with the Wolfram|Alpha API.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @group(name="wolfram", aliases=("wolf", "wa"), invoke_without_command=True)
    @custom_cooldown(*STAFF_ROLES)
    async def wolfram_command(self, ctx: Context, *, query: str) -> None:
        """
        Requests all answers on a single image,
        sends an image of all related pods

        :param ctx: Context
        :param query: str - string request to api
        """

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
        Requests a drawn image of given query
        Keywords worth noting are, "like curve", "curve", "graph", "pokemon", etc

        :param ctx: Context
        :param query: str - string request to api
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
    async def wolfram_cut_command(self, ctx, *, query: str) -> None:
        """
        Requests a drawn image of given query
        Keywords worth noting are, "like curve", "curve", "graph", "pokemon", etc

        :param ctx: Context
        :param query: str - string request to api
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
        """
            Requests an answer to a simple question
            Responds in plaintext

            :param ctx: Context
            :param query: str - string request to api
        """

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
            else:
                message = response_text
                color = Colours.soft_orange

            await send_embed(ctx, message, color)


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Wolfram(bot))
    log.info("Cog loaded: Wolfram")
