import os

from discord import Colour, Embed
from discord.ext.commands import AutoShardedBot, command, Context, cooldown
from aiohttp import ClientSession

from bot.constants import ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE
from bot.constants import SITE_API_DOCS_URL
from bot.decorators import with_role


class Docs:
    """
    Save new docs and fetch existing docs.
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    @cooldown(1, 60.0)
    @command(name="docs.get()", aliases=["docs.get"])
    async def get(self, ctx: Context, doc_name: str = None):
        """
        Get doc_data from api.pythondiscord.com

        :param ctx: Discord message context
        :param doc_name:
        If provided, this function shows data for that specific doc.
        If not provided, this function shows the caller a list of all docs.
        """

        headers = {"X-API-KEY": os.environ.get("BOT_API_KEY")}
        params = {}
        embed = Embed()

        if doc_name:
            params = {'doc_name': doc_name}

        async with ClientSession() as session:
            response = await session.get(SITE_API_DOCS_URL, headers=headers, params=params)
            result = await response.json()

        # doc not found
        if result:
            embed.colour = Colour.blurple()
            embed.title = doc_name
            if isinstance(result, list):
                embed.description = "\n".join(result)
            else:
                embed.description = result['doc_content']

        else:
            embed.colour = Colour.red()
            embed.title = "doc not found!"
            if isinstance(result, dict):
                embed.description = f"Unknown doc: {doc_name}"

        return await ctx.send(embed=embed)

    @with_role(ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE)
    @command(name="docs.set()", aliases=["docs.set, docs.add, docs.add(), docs.edit, docs.edit()"])
    async def set_doc(self, ctx: Context, doc_name: str, doc_content: str):
        """
        Set doc_data using api.pythondiscord.com.
        Either creates a new doc or edits an existing one.

        :param ctx: discord message context
        :param doc_name: The name of the doc to create or edit.
        :param doc_content: The content of the doc.
        """

        headers = {"X-API-KEY": os.environ.get("BOT_API_KEY")}
        params = {}
        embed = Embed()

        if doc_name and doc_content:
            params = {
                'doc_name': doc_name,
                'doc_content': doc_content
            }
        else:
            embed.colour = Colour.red(),
            embed.title = "Missing parameters!",
            embed.description = "This method requires both doc_name and doc_content"
            return await ctx.send(embed=embed)

        async with ClientSession() as session:
            response = await session.post(SITE_API_DOCS_URL,
                                          headers=headers,
                                          json=params)
            result = await response.json()

        if result.get("success"):
            embed.colour = Colour.blurple()
            embed.title = doc_name
            embed.description = f"doc successfully added: {doc_name}"
        else:
            embed.colour = Colour.red()
            embed.title = "doc not found!"
            embed.description = str(result)
            # embed.description = f"Unknown doc: {doc_name}"

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Docs(bot))
    print("Cog loaded: docs")