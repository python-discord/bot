import logging
from random import choice

from discord import Embed
from discord.ext.commands import Cog, Context, command

from bot.bot import Bot
from bot.constants import NEGATIVE_REPLIES, Colours

URL = "https://pypi.org/pypi/{package}/json"
FIELDS = ["author", "requires_python", "description", "license"]

log = logging.getLogger(__name__)


class PyPi(Cog):
    """Cog for getting information about PyPi packages."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @command(name="pypi", aliases=("package", "pack"))
    async def get_package_info(self, ctx: Context, package: str) -> None:
        """Getting information about a specific package."""
        embed = Embed(title=choice(NEGATIVE_REPLIES), colour=Colours.soft_red)

        async with self.bot.http_session.get(URL.format(package=package)) as response:
            if response.status == 404:
                embed.description = f"Package could not be found."

            elif response.status == 200 and response.content_type == "application/json":
                response_json = await response.json()
                info = response_json["info"]

                embed.title = "Python Package Index"
                embed.colour = Colours.soft_green
                embed.description = f"[{info['name']} v{info['version']}]({info['download_url']})\n"

                for field in FIELDS:
                    embed.add_field(
                        name=field.replace("_", " ").title(),
                        value=info[field],
                        inline=False,
                    )

            else:
                embed.description = "There was an error when fetching your PyPi package."
                log.trace(f"Error when fetching PyPi package: {response.status}.")

        await ctx.send(embed=embed)


def setup(bot: Bot) -> None:
    """Load the PyPi cog."""
    bot.add_cog(PyPi(bot))
