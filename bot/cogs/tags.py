import logging
import random
import time
from typing import Optional

from discord import Colour, Embed
from discord.ext.commands import (
    BadArgument, Bot,
    Context, Converter, group
)

from bot.constants import (
    Channels, Cooldowns, ERROR_REPLIES, Keys, Roles, URLs
)
from bot.converters import ValidURL
from bot.decorators import with_role
from bot.pagination import LinePaginator


log = logging.getLogger(__name__)

TEST_CHANNELS = (
    Channels.devtest,
    Channels.bot,
    Channels.helpers
)


class TagNameConverter(Converter):
    @staticmethod
    async def convert(ctx: Context, tag_name: str):
        def is_number(value):
            try:
                float(value)
            except ValueError:
                return False
            return True

        tag_name = tag_name.lower().strip()

        # The tag name has at least one invalid character.
        if ascii(tag_name)[1:-1] != tag_name:
            log.warning(f"{ctx.author} tried to put an invalid character in a tag name. "
                        "Rejecting the request.")
            raise BadArgument("Don't be ridiculous, you can't use that character!")

        # The tag name is either empty, or consists of nothing but whitespace.
        elif not tag_name:
            log.warning(f"{ctx.author} tried to create a tag with a name consisting only of whitespace. "
                        "Rejecting the request.")
            raise BadArgument("Tag names should not be empty, or filled with whitespace.")

        # The tag name is a number of some kind, we don't allow that.
        elif is_number(tag_name):
            log.warning(f"{ctx.author} tried to create a tag with a digit as its name. "
                        "Rejecting the request.")
            raise BadArgument("Tag names can't be numbers.")

        # The tag name is longer than 127 characters.
        elif len(tag_name) > 127:
            log.warning(f"{ctx.author} tried to request a tag name with over 127 characters. "
                        "Rejecting the request.")
            raise BadArgument("Are you insane? That's way too long!")

        return tag_name


class TagContentConverter(Converter):
    @staticmethod
    async def convert(ctx: Context, tag_content: str):
        tag_content = tag_content.strip()

        # The tag contents should not be empty, or filled with whitespace.
        if not tag_content:
            log.warning(f"{ctx.author} tried to create a tag containing only whitespace. "
                        "Rejecting the request.")
            raise BadArgument("Tag contents should not be empty, or filled with whitespace.")

        return tag_content


class Tags:
    """
    Save new tags and fetch existing tags.
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self.tag_cooldowns = {}
        self.headers = {"Authorization": f"Token {Keys.site_api}"}

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
    async def tags_group(self, ctx: Context, *, tag_name: TagNameConverter=None):
        """Show all known tags, a single tag, or run a subcommand."""

        await ctx.invoke(self.get_command, tag_name=tag_name)

    @tags_group.command(name='get', aliases=('show', 'g'))
    async def get_command(self, ctx: Context, *, tag_name: TagNameConverter=None):
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

        if tag_name is not None:
            tag = await self.bot.api_client.get(f'bot/tags/{tag_name}')
            if ctx.channel.id not in TEST_CHANNELS:
                self.tag_cooldowns[tag_name] = {
                    "time": time.time(),
                    "channel": ctx.channel.id
                }
            await ctx.send(embed=Embed.from_data(tag['embed']))

        else:
            tags = await self.bot.api_client.get('bot/tags')
            if not tags:
                await ctx.send(embed=Embed(
                    description="**There are no tags in the database!**",
                    colour=Colour.red()
                ))
            else:
                embed = Embed(title="**Current tags**")
                await LinePaginator.paginate(
                    sorted(f"**»**   {tag['title']}" for tag in tags),
                    ctx,
                    embed,
                    footer_text="To show a tag, type !tags <tagname>.",
                    empty=False,
                    max_lines=15
                )

    @tags_group.command(name='set', aliases=('add', 's'))
    @with_role(Roles.admin, Roles.owner, Roles.moderator)
    async def set_command(
        self,
        ctx: Context,
        tag_name: TagNameConverter,
        *,
        tag_content: TagContentConverter,
    ):
        """
        Create a new tag or update an existing one.

        :param ctx: discord message context
        :param tag_name: The name of the tag to create or edit.
        :param tag_content: The content of the tag.
        """

        body = {
            'title': tag_name.lower().strip(),
            'embed': {
                'title': tag_name,
                'description': tag_content
            }
        }

        await self.bot.api_client.post('bot/tags', json=body)

        log.debug(f"{ctx.author} successfully added the following tag to our database: \n"
                  f"tag_name: {tag_name}\n"
                  f"tag_content: '{tag_content}'\n")

        await ctx.send(embed=Embed(
            title="Tag successfully added",
            description=f"**{tag_name}** added to tag database.",
            colour=Colour.blurple()
        ))

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


def setup(bot):
    bot.add_cog(Tags(bot))
    log.info("Cog loaded: Tags")
