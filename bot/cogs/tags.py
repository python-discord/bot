import time

from aiohttp import ClientSession

from discord import Colour, Embed
from discord.ext.commands import AutoShardedBot, Context, command

from bot.constants import ADMIN_ROLE, MODERATOR_ROLE, OWNER_ROLE
from bot.constants import SITE_API_KEY, SITE_API_TAGS_URL, TAG_COOLDOWN
from bot.decorators import with_role
from bot.utils import paginate


class Tags:
    """
    Save new tags and fetch existing tags.
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot
        self.tag_cooldowns = {}
        self.headers = {"X-API-KEY": SITE_API_KEY}

    async def get_tag_data(self, tag_name=None) -> dict:
        """
        Retrieve the tag_data from our API

        :param tag_name: the tag to retrieve
        :return:
        if tag_name was provided, returns a dict with tag data.
        if not, returns a list of dicts with all tag data.

        """
        params = {}

        if tag_name:
            params['tag_name'] = tag_name

        async with ClientSession() as session:
            response = await session.get(SITE_API_TAGS_URL, headers=self.headers, params=params)
            tag_data = await response.json()

        return tag_data

    async def post_tag_data(self, tag_name: str, tag_content: str) -> dict:
        """
        Send some tag_data to our API to have it saved in the database.

        :param tag_name: The name of the tag to create or edit.
        :param tag_content: The content of the tag.
        :return: json response from the API in the following format:
        {
            'success': bool
        }
        """

        params = {
            'tag_name': tag_name,
            'tag_content': tag_content
        }

        async with ClientSession() as session:
            response = await session.post(SITE_API_TAGS_URL, headers=self.headers, json=params)
            tag_data = await response.json()

        return tag_data

    async def delete_tag_data(self, tag_name: str) -> dict:
        """
        Delete a tag using our API.

        :param tag_name: The name of the tag to delete.
        :return: json response from the API in the following format:
        {
            'success': bool
        }
        """

        params = {}

        if tag_name:
            params['tag_name'] = tag_name

        async with ClientSession() as session:
            response = await session.delete(SITE_API_TAGS_URL, headers=self.headers, json=params)
            tag_data = await response.json()

        return tag_data

    @command(name="tags()", aliases=["tags"], hidden=True)
    async def info_command(self, ctx: Context):
        """
        Show available methods for this class.

        :param ctx: Discord message context
        """

        return await ctx.invoke(self.bot.get_command("help"), "Tags")

    @command(name="tags.get()", aliases=["tags.get", "tags.show()", "tags.show", "get_tag"])
    async def get_command(self, ctx: Context, tag_name=None):
        """
        Get a list of all tags or a specified tag.

        :param ctx: Discord message context
        :param tag_name:
        If provided, this function shows data for that specific tag.
        If not provided, this function shows the caller a list of all tags.
        """

        def _command_on_cooldown(tag_name) -> bool:
            """
            Check if the command is currently on cooldown.
            The cooldown duration is set in constants.py.

            This works on a per-tag, per-channel basis.
            :param tag_name: The name of the command to check.
            :return: True if the command is cooling down. Otherwise False.
            """

            now = time.time()

            cooldown_conditions = (
                tag_name
                and tag_name in self.tag_cooldowns
                and (now - self.tag_cooldowns[tag_name]["time"]) < TAG_COOLDOWN
                and self.tag_cooldowns[tag_name]["channel"] == ctx.channel.id
            )

            if cooldown_conditions:
                return True
            return False

        if _command_on_cooldown(tag_name):
            time_left = TAG_COOLDOWN - (time.time() - self.tag_cooldowns[tag_name]["time"])
            print(f"That command is currently on cooldown. Try again in {time_left:.1f} seconds.")
            return

        embed = Embed()
        tags = []

        tag_data = await self.get_tag_data(tag_name)

        # If we found something, prepare that data
        if tag_data:
            embed.colour = Colour.blurple()

            if tag_name:
                embed.title = tag_name
                self.tag_cooldowns[tag_name] = {
                    "time": time.time(),
                    "channel": ctx.channel.id
                }

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
            embed.description = "**There are no tags in the database!**"

            if isinstance(tag_data, dict):
                embed.description = f"Unknown tag: **{tag_name}**"

            if tag_name:
                embed.set_footer(text="To show a list of all tags, use bot.tags.get().")
                embed.title = "Tag not found"

        # Paginate if this is a list of all tags
        if tags:
            return await paginate(
                (lines for lines in tags),
                ctx, embed,
                footer_text="To show a tag, type bot.tags.get <tagname>.",
                empty=False,
                max_size=200
            )

        return await ctx.send(embed=embed)

    @with_role(ADMIN_ROLE, OWNER_ROLE, MODERATOR_ROLE)
    @command(name="tags.set()", aliases=["tags.set", "tags.add", "tags.add()", "tags.edit", "tags.edit()", "add_tag"])
    async def set_command(self, ctx: Context, tag_name: str, tag_content: str):
        """
        Create a new tag or edit an existing one.

        :param ctx: discord message context
        :param tag_name: The name of the tag to create or edit.
        :param tag_content: The content of the tag.
        """

        embed = Embed()
        embed.colour = Colour.red()

        if "\n" in tag_name:
            embed.title = "Please don't do that"
            embed.description = "Don't be ridiculous. Newlines are obviously not allowed in the tag name."

        elif tag_name.isdigit():
            embed.title = "Please don't do that"
            embed.description = "Tag names can't be numbers."

        elif not tag_content.strip():
            embed.title = "Please don't do that"
            embed.description = "Tags should not be empty, or filled with whitespace."

        else:
            if not (tag_name and tag_content):
                embed.title = "Missing parameters"
                embed.description = "The tag needs both a name and some content."
                return await ctx.send(embed=embed)

            tag_name = tag_name.lower()
            tag_data = await self.post_tag_data(tag_name, tag_content)

            if tag_data.get("success"):
                embed.colour = Colour.blurple()
                embed.title = "Tag successfully added"
                embed.description = f"**{tag_name}** added to tag database."
            else:
                embed.title = "Database error"
                embed.description = ("There was a problem adding the data to the tags database. "
                                     "Please try again. If the problem persists, check the API logs.")

        return await ctx.send(embed=embed)

    @with_role(ADMIN_ROLE, OWNER_ROLE)
    @command(name="tags.delete()", aliases=["tags.delete", "tags.remove", "tags.remove()", "remove_tag"])
    async def delete_command(self, ctx: Context, tag_name: str):
        """
        Remove a tag from the database.

        :param ctx: discord message context
        :param tag_name: The name of the tag to delete.
        """

        embed = Embed()
        embed.colour = Colour.red()

        if not tag_name:
            embed.title = "Missing parameters"
            embed.description = "This method requires a `tag_name` parameter."
            return await ctx.send(embed=embed)

        tag_data = await self.delete_tag_data(tag_name)

        if tag_data.get("success"):
            embed.colour = Colour.blurple()
            embed.title = tag_name
            embed.description = f"Tag successfully removed: {tag_name}."

        else:
            embed.title = "Database error",
            embed.description = ("There was a problem deleting the data from the tags database. "
                                 "Please try again. If the problem persists, check the API logs.")

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Tags(bot))
    print("Cog loaded: Tags")
