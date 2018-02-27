import os

from aiohttp import ClientSession

from discord import Colour, Embed
from discord.ext.commands import AutoShardedBot, Context, command

from bot.constants import ADMIN_ROLE, MODERATOR_ROLE, OWNER_ROLE
from bot.constants import SITE_API_TAGS_URL
from bot.decorators import with_role


class Tags:
    """
    Save new tags and fetch existing tags.
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    @command(name="tags.get()", aliases=["tags.get"])
    async def get(self, ctx: Context, tag_name: str = None):
        """
        Get tag_data from api.pythondiscord.com

        :param ctx: Discord message context
        :param tag_name:
        If provided, this function shows data for that specific tag.
        If not provided, this function shows the caller a list of all tags.
        """

        headers = {"X-API-KEY": os.environ.get("BOT_API_KEY")}
        params = {}
        embed = Embed()

        if tag_name:
            params['tag_name'] = tag_name

        async with ClientSession() as session:
            response = await session.get(SITE_API_TAGS_URL, headers=headers, params=params)
            result = await response.json()

        # tag not found
        if result:
            embed.colour = Colour.blurple()

            if tag_name:
                embed.title = tag_name
            else:
                embed.title = "**Current tags**"

            if isinstance(result, list):
                names = [f"»   {tag_data['tag_name']}" for tag_data in result]
                if len(names) > 1:
                    names = "\n".join(sorted(names))
                    embed.description = names
                    embed.footer = "To show a tag, type `bot.tags.get <tagname>`"
                else:
                    embed.description = names[0]

            else:
                embed.description = result['tag_content']

        else:
            embed.colour = Colour.red()
            embed.title = "tag not found!"
            if isinstance(result, dict):
                embed.description = f"Unknown tag: {tag_name}"
            embed.footer = "To show a list of all tags, use `bot.tags.get()`"

        return await ctx.send(embed=embed)

    @with_role(ADMIN_ROLE, OWNER_ROLE, MODERATOR_ROLE)
    @command(name="tags.set()", aliases=["tags.set", "tags.add", "tags.add()", "tags.edit", "tags.edit()"])
    async def set(self, ctx: Context, tag_name: str, tag_content: str):
        """
        Set tag_data using api.pythondiscord.com.
        Either creates a new tag or edits an existing one.

        :param ctx: discord message context
        :param tag_name: The name of the tag to create or edit.
        :param tag_content: The content of the tag.
        """

        headers = {"X-API-KEY": os.environ.get("BOT_API_KEY")}
        params = {}
        embed = Embed()

        if tag_name and tag_content:
            params["tag_name"] = tag_name
            params["tag_content"] = tag_content

        else:
            embed.colour = Colour.red(),
            embed.title = "Missing parameters!",
            embed.description = "This method requires both tag_name and tag_content"
            return await ctx.send(embed=embed)

        async with ClientSession() as session:
            response = await session.post(SITE_API_TAGS_URL,
                                          headers=headers,
                                          json=params)
            result = await response.json()

        if result.get("success"):
            embed.colour = Colour.blurple()
            embed.description = f"tag successfully added: {tag_name}"
        else:
            # something terrible happened. we should probably log or something.
            pass

        return await ctx.send(embed=embed)

    @with_role(ADMIN_ROLE, OWNER_ROLE)
    @command(name="tags.delete()", aliases=["tags.delete", "tags.remove", "tags.remove()"])
    async def delete(self, ctx: Context, tag_name: str):
        """
        Delete a tag using api.pythondiscord.com.

        :param ctx: discord message context
        :param tag_name: The name of the tag to delete.
        """

        headers = {"X-API-KEY": os.environ.get("BOT_API_KEY")}
        params = {}
        embed = Embed()

        if tag_name:
            params['tag_name'] = tag_name

        else:
            embed.colour = Colour.red(),
            embed.title = "Missing parameters!",
            embed.description = "This method requires a `tag_name` parameter"
            return await ctx.send(embed=embed)

        async with ClientSession() as session:
            response = await session.delete(SITE_API_TAGS_URL,
                                            headers=headers,
                                            json=params)
            result = await response.json()

        if result.get("success"):
            embed.colour = Colour.blurple()
            embed.title = tag_name
            embed.description = f"tag successfully removed: {tag_name}"

        else:
            embed.colour = Colour.red()
            embed.title = "Tag not found!"
            embed.description = str(result)

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Tags(bot))
    print("Cog loaded: Tags")
