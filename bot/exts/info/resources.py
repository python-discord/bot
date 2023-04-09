import re
from urllib.parse import quote

from discord import Embed
from discord.ext import commands

from bot.bot import Bot

REGEX_CONSECUTIVE_NON_LETTERS = r"[^A-Za-z0-9]+"
RESOURCE_URL = "https://www.pythondiscord.com/resources/"


def to_kebabcase(resource_topic: str) -> str:
    """
    Convert any string to kebab-case.

    For example, convert
    "__Favorite FROOT¤#/$?is----LeMON???" to
    "favorite-froot-is-lemon"

    Code adopted from:
    https://github.com/python-discord/site/blob/main/pydis_site/apps/resources/templatetags/to_kebabcase.py
    """
    # First, make it lowercase, and just remove any apostrophes.
    # We remove the apostrophes because "wasnt" is better than "wasn-t"
    resource_topic = resource_topic.casefold()
    resource_topic = resource_topic.replace("'", "")

    # Now, replace any non-alphanumerics that remains with a dash.
    # If there are multiple consecutive non-letters, just replace them with a single dash.
    # my-favorite-class is better than my-favorite------class
    resource_topic = re.sub(
        REGEX_CONSECUTIVE_NON_LETTERS,
        "-",
        resource_topic,
    )

    # Now we use strip to get rid of any leading or trailing dashes.
    resource_topic = resource_topic.strip("-")
    return resource_topic


class Resources(commands.Cog):
    """Display information about the Python Discord website Resource page."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.command(name="resources", aliases=("res",))
    async def resources_command(self, ctx: commands.Context, *, resource_topic: str | None) -> None:
        """Display information and a link to the Python Discord website Resources page."""
        url = RESOURCE_URL

        if resource_topic:
            # Capture everything prior to new line allowing users to add messages below the command then prep for url
            url = f"{url}?topics={quote(to_kebabcase(resource_topic.splitlines()[0]))}"

        embed = Embed(
            title="Resources",
            description=f"The [Resources page]({url}) on our website contains a list "
                        f"of hand-selected learning resources that we "
                        f"regularly recommend to both beginners and experts."
        )
        await ctx.send(embed=embed)


async def setup(bot: Bot) -> None:
    """Load the Resources cog."""
    await bot.add_cog(Resources(bot))
