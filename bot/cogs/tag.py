import os

from aiohttp import ClientSession

GET_TAG_URL = "https://api.pythondiscord.com/tag"


class Tag:
    """
    Save new tags and fetch existing tags.
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

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

        return await result


t = Tag()
print(t.rget_tag("jonas"))


def setup(bot):
    bot.add_cog(Tag(bot))
    print("Cog loaded: Events")