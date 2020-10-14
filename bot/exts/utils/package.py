import logging
import random
from typing import Dict, Union

from aiohttp.client_exceptions import ContentTypeError
from discord import Embed
from discord.ext import commands

from bot.bot import Bot
from bot.constants import Colours, NEGATIVE_REPLIES

log = logging.getLogger(__name__)

pypi_api_url = "https://pypi.org/pypi/{package_name}/json"


class Package(commands.Cog):
    """Provides Information about package hosted at pypi."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @staticmethod
    def embed_builder(pypi_pkg: dict) -> Embed:
        """Returns informative embed about package."""
        embed = Embed()
        embed.colour = Colours.soft_orange
        embed.set_thumbnail(url="https://miro.medium.com/max/660/1*2FrV8q6rPdz6w2ShV6y7bw.png")

        links = []

        for pkg_info_heading, pkg_info in pypi_pkg.items():

            if pkg_info:  # Validating if package field is not a bank string
                pkg_info_heading = pkg_info_heading.replace("_", " ")

                if pkg_info_heading == "Package Name":
                    embed.title = pkg_info

                elif pkg_info_heading == "Summary":
                    embed.description = pkg_info

                elif str(pkg_info).startswith("https"):
                    links.append(f"[{pkg_info_heading}]({pkg_info})")

                else:
                    embed.add_field(name=pkg_info_heading, value=pkg_info, inline=False)

        if links:
            embed.add_field(name="Important Links", value="\n".join(links), inline=False)

        return embed

    @staticmethod
    def invalid_embed(invalid_package_name: str) -> Embed:
        """Genrates embed with error message for invalid package name."""
        embed = Embed()
        embed.color = Colours.soft_red
        embed.title = random.choice(NEGATIVE_REPLIES)
        embed.description = f"`{invalid_package_name}` is not a valid package name."

        return embed

    async def search_pypi(self, package_name: str) -> Dict[str, Union[str, int]]:
        """Collects information from pypi."""
        async with self.bot.http_session.get(pypi_api_url.format(package_name=package_name)) as response:

            a = await response.json()

            info = {"Package_Name": a["info"]["name"],
                    "Summary": a["info"]["summary"],
                    "Author": a["info"]["author"],
                    "Maintainer": a["info"]["maintainer"],
                    "Requires_python": a["info"]["requires_python"],
                    "Latest_version": a["info"]["version"],
                    "License": a["info"]["license"],
                    "Package_URL": a["info"]["package_url"],
                    "Homepage": a["info"]["home_page"]
                    }

        return info

    @commands.command(name="package", aliases=["pypi", "pkg"])
    async def pypi(self, ctx: commands.Context, package_name: str) -> None:
        """Provides information about pypi packages by taking package name as input."""
        async with ctx.typing():
            try:
                final_result = await self.search_pypi(package_name=package_name)
                log.trace("Valid name provided by the user.")
                final_embed = self.embed_builder(pypi_pkg=final_result)

            except ContentTypeError:
                log.info("Invalid name provided by the user.")
                final_embed = self.invalid_embed(invalid_package_name=package_name)

            await ctx.send(embed=final_embed)


def setup(bot: Bot) -> None:
    """Load the Package cog."""
    bot.add_cog(Package(bot))
