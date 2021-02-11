from discord import Embed
from discord.ext.commands import Cog, Context, command

from bot.bot import Bot
from bot.constants import NEGATIVE_REPLIES

URL = "https://pypi.org/pypi/{package}/json"


class PyPi(Cog):
    """Cog for getting information about PyPi packages."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @command(name="pypi", aliases=("package", "pack"))
    async def get_package_info(self, ctx: Context, package: str) -> None:
        """Getting information about a specific package."""
        embed = Embed(title="PyPi package information")

        async with self.bot.http_session.get(URL.format(package_name=package)) as response:
            if response.status == 404:
                return await ctx.send(f"Package with name '{package}' could not be found.")
            elif response.status == 200 and response.content_type == "application/json":
                response_json = await response.json()
                info = response_json["info"]
            else:
                return await ctx.send("There was an error when fetching your PyPi package.")

        await ctx.send(embed=embed)


def setup(bot: Bot) -> None:
    """Load the PyPi cog."""
    bot.add_cog(PyPi(bot))
