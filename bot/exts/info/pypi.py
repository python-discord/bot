import logging
from random import choice

from discord import Embed
from discord.ext.commands import Cog, Context, command

from bot.bot import Bot
from bot.constants import Colours, NEGATIVE_REPLIES

URL = "https://pypi.org/pypi/{package}/json"
FIELDS = ["author", "requires_python", "summary", "license"]

log = logging.getLogger(__name__)


class PyPi(Cog):
    """Cog for getting information about PyPi packages."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @command(name="pypi", aliases=("package", "pack"))
    async def get_package_info(self, ctx: Context, package: str) -> None:
        """Provide information about a specific package  from PyPI."""
        embed = Embed(title=choice(NEGATIVE_REPLIES), colour=Colours.soft_red)

        async with self.bot.http_session.get(URL.format(package=package)) as response:
            if response.status == 404:
                embed.description = "Package could not be found."

            elif response.status == 200 and response.content_type == "application/json":
                response_json = await response.json()
                info = response_json["info"]

                embed.title = f"{info['name']} v{info['version']}"
                embed.url = info['package_url']
                embed.colour = Colours.soft_green

                for field in FIELDS:
                    # Field could be completely empty, in some cases can be a string with whitespaces, or None.
                    if info[field] and not info[field].isspace():
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
