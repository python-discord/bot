import itertools
import random
import re
import typing
from contextlib import suppress
from datetime import datetime

from discord import Embed, NotFound
from discord.ext.commands import Cog, Context, command
from discord.utils import escape_markdown

from bot.bot import Bot
from bot.constants import Colours, NEGATIVE_REPLIES, RedirectOutput
from bot.log import get_logger
from bot.utils import time
from bot.utils.messages import wait_for_deletion

URL = "https://pypi.org/pypi/{package}/json"
PYPI_ICON = "https://cdn.discordapp.com/emojis/766274397257334814.png"

PYPI_COLOURS = itertools.cycle((Colours.yellow, Colours.blue, Colours.white))

ILLEGAL_CHARACTERS = re.compile(r"[^-_.a-zA-Z0-9]+")
INVALID_INPUT_DELETE_DELAY = RedirectOutput.delete_delay

log = get_logger(__name__)

def _get_latest_distribution_timestamp(data: dict[str, typing.Any]) -> datetime | None:
    """Get upload date of last distribution, or `None` if no distributions were found."""
    if not data["urls"]:
        return None

    try:
        return time.discord_timestamp(data["urls"][-1]["upload_time_iso_8601"], time.TimestampFormats.DATE)
    except KeyError:
        log.trace("KeyError trying to fetch upload time: data['urls'][-1]['upload_time_iso_8601']")
        return None

class PyPi(Cog):
    """Cog for getting information about PyPi packages."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @command(name="pypi", aliases=("package", "pack", "pip"))
    async def get_package_info(self, ctx: Context, package: str) -> None:
        """Provide information about a specific package from PyPI."""
        embed = Embed(title=random.choice(NEGATIVE_REPLIES), colour=Colours.soft_red)
        embed.set_thumbnail(url=PYPI_ICON)

        error = True

        if characters := re.search(ILLEGAL_CHARACTERS, package):
            embed.description = f"Illegal character(s) passed into command: '{escape_markdown(characters.group(0))}'"

        else:
            async with self.bot.http_session.get(URL.format(package=package)) as response:
                if response.status == 404:
                    embed.description = "Package could not be found."

                elif response.status == 200 and response.content_type == "application/json":
                    response_json = await response.json()
                    info = response_json["info"]

                    embed.title = f"{info['name']} v{info['version']}"

                    embed.url = info["package_url"]
                    embed.colour = next(PYPI_COLOURS)

                    # Summary can be None if not provided by the package
                    summary: str | None = info["summary"]

                    # Summary could be completely empty, or just whitespace.
                    if summary and not summary.isspace():
                        embed.description = escape_markdown(summary)
                    else:
                        embed.description = "No summary provided."

                    upload_date = _get_latest_distribution_timestamp(response_json)
                    if upload_date:
                        embed.description += f"\n\nReleased on {upload_date}."

                    error = False

                else:
                    embed.description = "There was an error when fetching your PyPi package."
                    log.trace(f"Error when fetching PyPi package: {response.status}.")

        if error:
            error_message = await ctx.send(embed=embed)
            await wait_for_deletion(error_message, (ctx.author.id,), timeout=INVALID_INPUT_DELETE_DELAY)

            # Make sure that we won't cause a ghost-ping by deleting the message
            if not (ctx.message.mentions or ctx.message.role_mentions):
                with suppress(NotFound):
                    await ctx.message.delete()
                    await error_message.delete()

        else:
            await ctx.send(embed=embed)


async def setup(bot: Bot) -> None:
    """Load the PyPi cog."""
    await bot.add_cog(PyPi(bot))
