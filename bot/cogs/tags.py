import logging
import random
import time
from typing import Optional

from discord import Colour, Embed, User
from discord.ext.commands import AutoShardedBot, Context, command

from bot.constants import ADMIN_ROLE, MODERATOR_ROLE, OWNER_ROLE, SITE_API_KEY, SITE_API_TAGS_URL, TAG_COOLDOWN
from bot.decorators import with_role
from bot.pagination import LinePaginator

log = logging.getLogger(__name__)


class Tags:
    """
    Save new tags and fetch existing tags.
    """

    FAIL_TITLES = [
        "Please don't do that.",
        "You silly tart.",
        "You have to stop.",
        "Do you mind?",
        "In the future, don't do that.",
        "That was a mistake.",
        "You blew it.",
        "You're bad at computers.",
        "Are you trying to kill me?",
        "Noooooo!!"
    ]

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
            params["tag_name"] = tag_name

        response = await self.bot.http_session.get(SITE_API_TAGS_URL, headers=self.headers, params=params)
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

        response = await self.bot.http_session.post(SITE_API_TAGS_URL, headers=self.headers, json=params)
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

        response = await self.bot.http_session.delete(SITE_API_TAGS_URL, headers=self.headers, json=params)
        tag_data = await response.json()

        return tag_data

    @staticmethod
    async def validate(author: User, tag_name: str, tag_content: str = None) -> Optional[Embed]:
        """
        Create an embed based on the validity of a tag's name and content

        :param author: The user that called the command
        :param tag_name: The name of the tag to validate.
        :param tag_content: The tag's content, if any.
        :return: A validation embed if invalid, otherwise None
        """

        def is_number(value):
            try:
                float(value)
            except ValueError:
                return False
            else:
                return True

        embed = Embed()
        embed.colour = Colour.red()

        # 'tag_name' has at least one invalid character.
        if ascii(tag_name)[1:-1] != tag_name:
            log.warning(f"{author} tried to put an invalid character in a tag name. "
                        "Rejecting the request.")
            embed.title = random.choice(Tags.FAIL_TITLES)
            embed.description = "Don't be ridiculous, you can't use that character!"

        # 'tag_content' or 'tag_name' are either empty, or consist of nothing but whitespace
        elif (tag_content is not None and not tag_content) or not tag_name:
            log.warning(f"{author} tried to create a tag with a name consisting only of whitespace. "
                        "Rejecting the request.")
            embed.title = random.choice(Tags.FAIL_TITLES)
            embed.description = "Tags should not be empty, or filled with whitespace."

        # 'tag_name' is a number of some kind, we don't allow that.
        elif is_number(tag_name):
            log.error("inside the is_number")
            log.warning(f"{author} tried to create a tag with a digit as its name. "
                        "Rejecting the request.")
            embed.title = random.choice(Tags.FAIL_TITLES)
            embed.description = "Tag names can't be numbers."

        # 'tag_name' is longer than 127 characters
        elif len(tag_name) > 127:
            log.warning(f"{author} tried to request a tag name with over 127 characters. "
                        "Rejecting the request.")
            embed.title = random.choice(Tags.FAIL_TITLES)
            embed.description = "Are you insane? That's way too long!"

        else:
            return None
        return embed

    @command(name="tags()", aliases=["tags"], hidden=True)
    async def info_command(self, ctx: Context):
        """
        Show available methods for this class.

        :param ctx: Discord message context
        """

        log.debug(f"{ctx.author} requested info about the tags cog")
        return await ctx.invoke(self.bot.get_command("help"), "Tags")

    @command(name="tags.get()", aliases=["tags.get", "tags.show()", "tags.show", "get_tag"])
    async def get_command(self, ctx: Context, tag_name: str=None):
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
            log.warning(f"{ctx.author} tried to get the '{tag_name}' tag, but the tag is on cooldown. "
                        f"Cooldown ends in {time_left:.1f} seconds.")
            return

        tags = []

        if tag_name is not None:
            tag_name = tag_name.lower().strip()
            validation = await self.validate(ctx.author, tag_name)

            if validation is not None:
                return await ctx.send(embed=validation)

        embed = Embed()
        embed.colour = Colour.red()
        tag_data = await self.get_tag_data(tag_name)

        # If we found something, prepare that data
        if tag_data:
            embed.colour = Colour.blurple()

            if tag_name:
                log.debug(f"{ctx.author} requested the tag '{tag_name}'")
                embed.title = tag_name
                self.tag_cooldowns[tag_name] = {
                    "time": time.time(),
                    "channel": ctx.channel.id
                }

            else:
                embed.title = "**Current tags**"

            if isinstance(tag_data, list):
                log.debug(f"{ctx.author} requested a list of all tags")
                tags = [f"**»**   {tag['tag_name']}" for tag in tag_data]
                tags = sorted(tags)

            else:
                embed.description = tag_data['tag_content']

        # If not, prepare an error message.
        else:
            embed.colour = Colour.red()

            if isinstance(tag_data, dict):
                log.warning(f"{ctx.author} requested the tag '{tag_name}', but it could not be found.")
                embed.description = f"There wasn't a **{tag_name}** tag! Make sure you typed it correctly."
            else:
                log.warning(f"{ctx.author} requested a list of all tags, but the tags database was empty!")
                embed.description = "**There are no tags in the database!**"

            if tag_name:
                embed.set_footer(text="To show a list of all tags, use bot.tags.get().")
                embed.title = "Couldn't find that tag!"

        # Paginate if this is a list of all tags
        if tags:
            log.debug(f"Returning a paginated list of all tags.")
            return await LinePaginator.paginate(
                (lines for lines in tags),
                ctx, embed,
                footer_text="To show a tag, type bot.tags.get <tagname>.",
                empty=False,
                max_lines=15
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

        validation = await self.validate(ctx.author, tag_name, tag_content)

        if validation is not None:
            return await ctx.send(embed=validation)

        tag_name = tag_name.lower().strip()
        tag_content = tag_content.strip()

        embed = Embed()
        embed.colour = Colour.red()
        tag_data = await self.post_tag_data(tag_name, tag_content)

        if tag_data.get("success"):
            log.debug(f"{ctx.author} successfully added the following tag to our database: \n"
                      f"tag_name: {tag_name}\n"
                      f"tag_content: '{tag_content}'")
            embed.colour = Colour.blurple()
            embed.title = "Tag successfully added"
            embed.description = f"**{tag_name}** added to tag database."
        else:
            log.error("There was an unexpected database error when trying to add the following tag: \n"
                      f"tag_name: {tag_name}\n"
                      f"tag_content: '{tag_content}'\n"
                      f"response: {tag_data}")
            embed.title = "Database error"
            embed.description = ("There was a problem adding the data to the tags database. "
                                 "Please try again. If the problem persists, see the error logs.")

        return await ctx.send(embed=embed)

    @with_role(ADMIN_ROLE, OWNER_ROLE)
    @command(name="tags.delete()", aliases=["tags.delete", "tags.remove", "tags.remove()", "remove_tag"])
    async def delete_command(self, ctx: Context, tag_name: str):
        """
        Remove a tag from the database.

        :param ctx: discord message context
        :param tag_name: The name of the tag to delete.
        """

        validation = await self.validate(ctx.author, tag_name)

        if validation is not None:
            return await ctx.send(embed=validation)

        tag_name = tag_name.lower().strip()
        embed = Embed()
        embed.colour = Colour.red()
        tag_data = await self.delete_tag_data(tag_name)

        if tag_data.get("success") is True:
            log.debug(f"{ctx.author} successfully deleted the tag called '{tag_name}'")
            embed.colour = Colour.blurple()
            embed.title = tag_name
            embed.description = f"Tag successfully removed: {tag_name}."

        elif tag_data.get("success") is False:
            log.debug(f"{ctx.author} tried to delete a tag called '{tag_name}', but the tag does not exist.")
            embed.colour = Colour.red()
            embed.title = tag_name
            embed.description = "Tag doesn't appear to exist."

        else:
            log.error("There was an unexpected database error when trying to delete the following tag: \n"
                      f"tag_name: {tag_name}\n"
                      f"response: {tag_data}")
            embed.title = "Database error"
            embed.description = ("There was an unexpected error with deleting the data from the tags database. "
                                 "Please try again. If the problem persists, see the error logs.")

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Tags(bot))
    log.info("Cog loaded: Tags")
