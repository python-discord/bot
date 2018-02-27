import os
from typing import Union

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
        self.api_key = os.environ.get("BOT_API_KEY")

    async def get_tag_data(self, tag_name: Union[str, None] = None):
        """
        Retrieve the tag_data from our API

        :param tag_name: the tag to retrieve
        :return:
        if tag_name was provided, returns a dict with tag data.
        if not, returns a list of dicts with all tag data.

        """
        headers = {"X-API-KEY": self.api_key}
        params = {}

        if tag_name:
            params['tag_name'] = tag_name

        async with ClientSession() as session:
            response = await session.get(SITE_API_TAGS_URL, headers=headers, params=params)
            tag_data = await response.json()

        return tag_data

    async def post_tag_data(self, tag_name: str, tag_content: str):
        """
        Send some tag_data to our API to have it saved in the database.

        :param tag_name: The name of the tag to create or edit.
        :param tag_content: The content of the tag.
        :return: json response from the API in the following format:
        {
            'success': bool
        }
        """

        headers = {"X-API-KEY": self.api_key}
        params = {
            'tag_name': tag_name,
            'tag_content': tag_content
        }

        async with ClientSession() as session:
            response = await session.post(SITE_API_TAGS_URL, headers=headers, json=params)
            tag_data = await response.json()

        return tag_data

    async def delete_tag_data(self, tag_name: str):
        """
        Delete a tag using our API.

        :param tag_name: The name of the tag to delete.
        :return: json response from the API in the following format:
        {
            'success': bool
        }
        """

        headers = {"X-API-KEY": self.api_key}
        params = {}

        if tag_name:
            params['tag_name'] = tag_name

        async with ClientSession() as session:
            response = await session.delete(SITE_API_TAGS_URL, headers=headers, json=params)
            tag_data = await response.json()

        return tag_data

    @command(name="tags()", aliases=["tags"], hidden=True)
    async def info(self, ctx: Context):
        """
        Show available methods for this class.

        :param ctx: Discord message context
        """

        return await ctx.invoke(self.bot.get_command("help"), "Tags")

    @command(name="tags.get()", aliases=["tags.get", "tags.show()", "tags.show"])
    async def get(self, ctx: Context, tag_name: str = None):
        """
        Get a list of all tags or a specified tag.

        :param ctx: Discord message context
        :param tag_name:
        If provided, this function shows data for that specific tag.
        If not provided, this function shows the caller a list of all tags.
        """

        embed = Embed()
        tags = []
        tag_data = await self.get_tag_data(tag_name)

        # If we found something, prepare that data
        if tag_data:
            embed.colour = Colour.blurple()

            if tag_name:
                embed.title = tag_name
            else:
                embed.title = "**Current tags**"

            if isinstance(tag_data, list):
                tags = [f"**»**   {tag['tag_name']}" for tag in tag_data]
                tags = sorted(tags)

            else:
                embed.description = tag_data['tag_content']

        # If not, prepare an error message.
        else:
            embed.colour = Colour.red()
            embed.title = "There are no tags in the database!"

            if isinstance(tag_data, dict):
                embed.description = f"Unknown tag: **{tag_name}**"

            if tag_name:
                embed.set_footer(text="To show a list of all tags, use bot.tags.get()")
                embed.title = "Tag not found!"

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
        Create a new tag or edit an existing one.

        :param ctx: discord message context
        :param tag_name: The name of the tag to create or edit.
        :param tag_content: The content of the tag.
        """

        embed = Embed()

        if "\n" in tag_name:
            embed.colour = Colour.red()
            embed.title = "Please don't do that"
            embed.description = "Don't be ridiculous. Newlines are obviously not allowed in the tag name."

        else:
            if tag_name and tag_content:
                tag_name = tag_name.lower()
                tag_data = await self.post_tag_data(tag_name, tag_content)

            else:
                embed.colour = Colour.red(),
                embed.title = "Missing parameters!",
                embed.description = "The tag needs both a name and some content"
                return await ctx.send(embed=embed)

            if tag_data.get("success"):
                embed.colour = Colour.blurple()
                embed.title = "Tag successfully added!"
                embed.description = f"**{tag_name}** added to tag database."
            else:
                print(f"Something terrible happened. The API returned {tag_data}")

        return await ctx.send(embed=embed)

    @with_role(ADMIN_ROLE, OWNER_ROLE)
    @command(name="tags.delete()", aliases=["tags.delete", "tags.remove", "tags.remove()"])
    async def delete(self, ctx: Context, tag_name: str):
        """
        Remove a tag from the database.

        :param ctx: discord message context
        :param tag_name: The name of the tag to delete.
        """

        embed = Embed()

        if tag_name:
            tag_data = await self.delete_tag_data(tag_name)

        else:
            embed.colour = Colour.red(),
            embed.title = "Missing parameters!",
            embed.description = "This method requires a `tag_name` parameter"
            return await ctx.send(embed=embed)

        if tag_data.get("success"):
            embed.colour = Colour.blurple()
            embed.title = tag_name
            embed.description = f"tag successfully removed: {tag_name}"

        else:
            print(f"Something terrifying happened. The API returned {tag_data}")

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Tags(bot))
    print("Cog loaded: Tags")
