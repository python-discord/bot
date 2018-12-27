import logging
import random
import time
from typing import Optional

from discord import Colour, Embed
from discord.ext.commands import (
    BadArgument, Bot,
    Context, group
)

from bot.constants import (
    Channels, Cooldowns, ERROR_REPLIES, Keys, Roles, URLs
)
from bot.converters import TagContentConverter, TagNameConverter, ValidURL
from bot.decorators import with_role
from bot.pagination import LinePaginator


log = logging.getLogger(__name__)

TEST_CHANNELS = (
    Channels.devtest,
    Channels.bot,
    Channels.helpers
)


class Tags:
    """
    Save new tags and fetch existing tags.
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self.tag_cooldowns = {}
        self.headers = {"X-API-KEY": Keys.site_api}

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

        response = await self.bot.http_session.get(URLs.site_tags_api, headers=self.headers, params=params)
        tag_data = await response.json()

        return tag_data

    async def post_tag_data(self, tag_name: str, tag_content: str, image_url: Optional[str]) -> dict:
        """
        Send some tag_data to our API to have it saved in the database.

        :param tag_name: The name of the tag to create or edit.
        :param tag_content: The content of the tag.
        :param image_url: The image URL of the tag, can be `None`.
        :return: json response from the API in the following format:
        {
            'success': bool
        }
        """

        params = {
            'tag_name': tag_name,
            'tag_content': tag_content,
            'image_url': image_url
        }

        response = await self.bot.http_session.post(URLs.site_tags_api, headers=self.headers, json=params)
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

        response = await self.bot.http_session.delete(URLs.site_tags_api, headers=self.headers, json=params)
        tag_data = await response.json()

        return tag_data

    @group(name='tags', aliases=('tag', 't'), hidden=True, invoke_without_command=True)
    async def tags_group(self, ctx: Context, *, tag_name: TagNameConverter = None):
        """Show all known tags, a single tag, or run a subcommand."""

        await ctx.invoke(self.get_command, tag_name=tag_name)

    @tags_group.command(name='get', aliases=('show', 'g'))
    async def get_command(self, ctx: Context, *, tag_name: TagNameConverter = None):
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
                and (now - self.tag_cooldowns[tag_name]["time"]) < Cooldowns.tags
                and self.tag_cooldowns[tag_name]["channel"] == ctx.channel.id
            )

            if cooldown_conditions:
                return True
            return False

        if _command_on_cooldown(tag_name):
            time_left = Cooldowns.tags - (time.time() - self.tag_cooldowns[tag_name]["time"])
            log.warning(f"{ctx.author} tried to get the '{tag_name}' tag, but the tag is on cooldown. "
                        f"Cooldown ends in {time_left:.1f} seconds.")
            return

        tags = []

        embed: Embed = Embed()
        embed.colour = Colour.red()
        tag_data = await self.get_tag_data(tag_name)

        # If we found something, prepare that data
        if tag_data:
            embed.colour = Colour.blurple()

            if tag_name:
                log.debug(f"{ctx.author} requested the tag '{tag_name}'")
                embed.title = tag_name

                if ctx.channel.id not in TEST_CHANNELS:
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
                if tag_data['image_url'] is not None:
                    embed.set_image(url=tag_data['image_url'])

        # If its invoked from error handler just ignore it.
        elif hasattr(ctx, "invoked_from_error_handler"):
            return
        # If not, prepare an error message.
        else:
            embed.colour = Colour.red()

            if isinstance(tag_data, dict):
                log.warning(f"{ctx.author} requested the tag '{tag_name}', but it could not be found.")
                embed.description = f"**{tag_name}** is an unknown tag name. Please check the spelling and try again."
            else:
                log.warning(f"{ctx.author} requested a list of all tags, but the tags database was empty!")
                embed.description = "**There are no tags in the database!**"

            if tag_name:
                embed.set_footer(text="To show a list of all tags, use !tags.")
                embed.title = "Tag not found."

        # Paginate if this is a list of all tags
        if tags:
            log.debug(f"Returning a paginated list of all tags.")
            return await LinePaginator.paginate(
                (lines for lines in tags),
                ctx, embed,
                footer_text="To show a tag, type !tags <tagname>.",
                empty=False,
                max_lines=15
            )

        return await ctx.send(embed=embed)

    @tags_group.command(name='set', aliases=('add', 'edit', 's'))
    @with_role(Roles.admin, Roles.owner, Roles.moderator)
    async def set_command(
        self,
        ctx: Context,
        tag_name: TagNameConverter,
        tag_content: TagContentConverter,
        image_url: ValidURL = None
    ):
        """
        Create a new tag or edit an existing one.

        :param ctx: discord message context
        :param tag_name: The name of the tag to create or edit.
        :param tag_content: The content of the tag.
        :param image_url: An optional image for the tag.
        """

        tag_name = tag_name.lower().strip()
        tag_content = tag_content.strip()

        embed = Embed()
        embed.colour = Colour.red()
        tag_data = await self.post_tag_data(tag_name, tag_content, image_url)

        if tag_data.get("success"):
            log.debug(f"{ctx.author} successfully added the following tag to our database: \n"
                      f"tag_name: {tag_name}\n"
                      f"tag_content: '{tag_content}'\n"
                      f"image_url: '{image_url}'")
            embed.colour = Colour.blurple()
            embed.title = "Tag successfully added"
            embed.description = f"**{tag_name}** added to tag database."
        else:
            log.error("There was an unexpected database error when trying to add the following tag: \n"
                      f"tag_name: {tag_name}\n"
                      f"tag_content: '{tag_content}'\n"
                      f"image_url: '{image_url}'\n"
                      f"response: {tag_data}")
            embed.title = "Database error"
            embed.description = ("There was a problem adding the data to the tags database. "
                                 "Please try again. If the problem persists, see the error logs.")

        return await ctx.send(embed=embed)

    @tags_group.command(name='delete', aliases=('remove', 'rm', 'd'))
    @with_role(Roles.admin, Roles.owner)
    async def delete_command(self, ctx: Context, *, tag_name: TagNameConverter):
        """
        Remove a tag from the database.

        :param ctx: discord message context
        :param tag_name: The name of the tag to delete.
        """

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

    @get_command.error
    @set_command.error
    @delete_command.error
    async def command_error(self, ctx, error):
        if isinstance(error, BadArgument):
            embed = Embed()
            embed.colour = Colour.red()
            embed.description = str(error)
            embed.title = random.choice(ERROR_REPLIES)
            await ctx.send(embed=embed)
        else:
            log.error(f"Unhandled tag command error: {error} ({error.original})")


def setup(bot):
    bot.add_cog(Tags(bot))
    log.info("Cog loaded: Tags")
