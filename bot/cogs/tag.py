import os

from discord import Message
from discord.ext.commands import AutoShardedBot, command
from aiohttp import ClientSession

from bot.constants import ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE

GET_TAG_URL = "https://api.pythondiscord.com:8080/tag"


class Tags:
    """
    Save new tags and fetch existing tags.
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    @command(name="get_tag()", aliases=["bot.get_tag", "bot.get_tag()", "get_tag"])
    async def get_tag(tag_name: str = None):
        """
        Get tag_data from api.pythondiscord.com

        :param tag_name:
        If provided, this function shows data for that specific tag.
        If not provided, this function shows the caller a list of all tags.
        """

        headers = {"X-API-KEY": os.environ.get("BOT_API_KEY")}
        params = {}

        if tag_name:
            params = {'tag_name': tag_name}

        with ClientSession() as session:
            response = await session.get(GET_TAG_URL, headers=headers, params=params)
            result = await response.json()

        embed = Embed(
            description="A utility bot designed just for the Python server! Try `bot.help()` for more info.",
            url="https://github.com/discord-python/bot"
        )

        return await result

    @with_role(ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE)
    @command(name="redeploy()", aliases=["bot.redeploy", "bot.redeploy()", "redeploy"])
    async def save_tag

def setup(bot):
    bot.add_cog(Tags(bot))
    print("Cog loaded: Tags")