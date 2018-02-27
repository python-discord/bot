import os

from aiohttp import ClientSession

from discord import Colour, Embed
from discord.ext.commands import AutoShardedBot, Context, command

from bot.constants import ADMIN_ROLE, MODERATOR_ROLE, OWNER_ROLE
from bot.constants import SITE_API_TAGS_URL
from bot.decorators import with_role
from bot.utils import paginate


class Tags:
    """
    Save new tags and fetch existing tags.
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    @command(name="tags.get()", aliases=["tags.get"])
    async def get(self, ctx: Context, tag_name: str = None):
        """
        Get tag_data from our API.

        :param ctx: Discord message context
        :param tag_name:
        If provided, this function shows data for that specific tag.
        If not provided, this function shows the caller a list of all tags.
        """

        headers = {"X-API-KEY": os.environ.get("BOT_API_KEY")}
        params = {}
        tags = []
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
                tags = [f"»   {tag_data['tag_name']}" for tag_data in result]
                tags = sorted(tags)

            else:
                embed.description = result['tag_content']

        else:
            embed.colour = Colour.red()
            embed.title = "Tag not found!"
            if isinstance(result, dict):
                embed.description = f"Unknown tag: **{tag_name}**"
            embed.set_footer(text="To show a list of all tags, use bot.tags.get()")

        # Paginate if this is a list of all tags
        if tags:
            return await paginate(
                (lines for lines in tags),
                ctx, embed,
                footer_text="To show a tag, type bot.tags.get <tagname>",
                empty=False,
                max_size=200
            )

        return await ctx.send(embed=embed)

    @with_role(ADMIN_ROLE, OWNER_ROLE, MODERATOR_ROLE)
    @command(name="tags.set()", aliases=["tags.set", "tags.add", "tags.add()", "tags.edit", "tags.edit()"])
    async def set(self, ctx: Context, tag_name: str, tag_content: str):
        """
        Set tag_data using our API.
        Either creates a new tag or edits an existing one.

        :param ctx: discord message context
        :param tag_name: The name of the tag to create or edit.
        :param tag_content: The content of the tag.
        """

        headers = {"X-API-KEY": os.environ.get("BOT_API_KEY")}
        params = {}
        embed = Embed()

        if tag_name and tag_content:
            tag_name = tag_name.lower()
            params["tag_name"] = tag_name
            params["tag_content"] = tag_content

        else:
            embed.colour = Colour.red(),
            embed.title = "Missing parameters!",
            embed.description = "The tag needs both a name and some content"
            return await ctx.send(embed=embed)

        async with ClientSession() as session:
            response = await session.post(SITE_API_TAGS_URL,
                                          headers=headers,
                                          json=params)
            result = await response.json()

        if result.get("success"):
            embed.colour = Colour.blurple()
            embed.title = "Tag successfully added!"
            embed.description = f"**{tag_name}** added to tag database."
        else:
            # something terrible happened. we should probably log or something.
            pass

        if "\n" in tag_name:
            embed.colour = Colour.red()
            embed.title = "Please don't do that"
            embed.description = "Don't be ridiculous. '\\n' is obviously not allowed in the tag name."

        return await ctx.send(embed=embed)

    @with_role(ADMIN_ROLE, OWNER_ROLE)
    @command(name="tags.delete()", aliases=["tags.delete", "tags.remove", "tags.remove()"])
    async def delete(self, ctx: Context, tag_name: str):
        """
        Delete a tag using our API.

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
