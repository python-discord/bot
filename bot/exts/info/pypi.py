import itertools
import logging
import random
import re

from discord import Embed
from discord.ext.commands import Cog, Context, command
from discord.utils import escape_markdown

from bot.bot import Bot
from bot.constants import Colours, NEGATIVE_REPLIES, RedirectOutput

URL = "https://pypi.org/pypi/{package}/json"
FIELDS = ("author", "requires_python", "summary", "license")
PYPI_ICON = "https://cdn.discordapp.com/emojis/766274397257334814.png"

PYPI_COLOURS = itertools.cycle((Colours.yellow, Colours.blue, Colours.white))

ILLEGAL_CHARACTERS = re.compile(r"[^a-zA-Z0-9-.]+")
INVALID_INPUT_DELETE_DELAY = RedirectOutput.delete_delay

log = logging.getLogger(__name__)


class PyPi(Cog):
    """Cog for getting information about PyPi packages."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @command(name="pypi", aliases=("package", "pack"))
    async def get_package_info(self, ctx: Context, package: str) -> None:
        """Provide information about a specific package from PyPI."""
        embed = Embed(
            title=random.choice(NEGATIVE_REPLIES),
            colour=Colours.soft_red
        )
        embed.set_thumbnail(url=PYPI_ICON)

        error = True

        if (character := re.search(ILLEGAL_CHARACTERS, package)) is not None:
            embed.description = f"Illegal character passed into command: '{escape_markdown(character.group(0))}'"

        else:
            async with self.bot.http_session.get(URL.format(package=package)) as response:
                if response.status == 404:
                    embed.description = "Package could not be found."

                elif response.status == 200 and response.content_type == "application/json":
                    response_json = await response.json()
                    info = response_json["info"]

                    embed.title = f"{info['name']} v{info['version']}"
                    embed.url = info['package_url']
                    embed.colour = next(PYPI_COLOURS)

                    for field in FIELDS:
                        field_data = info[field]

                        # Field could be completely empty, in some cases can be a string with whitespaces, or None.
                        if field_data and not field_data.isspace():
                            if '\n' in field_data and field == "license":
                                field_data = field_data.split('\n')[0]

                            embed.add_field(
                                name=field.replace("_", " ").title(),
                                value=escape_markdown(field_data),
                                inline=False,
                            )

                    error = False

                else:
                    embed.description = "There was an error when fetching your PyPi package."
                    log.trace(f"Error when fetching PyPi package: {response.status}.")

        if error:
            await ctx.send(embed=embed, delete_after=INVALID_INPUT_DELETE_DELAY)
            await ctx.message.delete(delay=INVALID_INPUT_DELETE_DELAY)
        else:
            await ctx.send(embed=embed)


def setup(bot: Bot) -> None:
    """Load the PyPi cog."""
    bot.add_cog(PyPi(bot))
