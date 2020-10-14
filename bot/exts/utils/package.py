import logging
from typing import Dict, Union

from discord import Embed
from discord.ext import commands

from bot.bot import Bot
from bot.constants import Colours

log = logging.getLogger(__name__)

package_url = "https://pypi.org/pypi/{package_name}/json"


class Package(commands.Cog):
    """Provides Information about package hosted at pypl."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @staticmethod
    def embed_builder(search_pypl: dict) -> Embed:
        """Returns informative embed about package."""
        embed = Embed()
        embed.colour = Colours.soft_orange
        embed.set_thumbnail(url="https://miro.medium.com/max/660/1*2FrV8q6rPdz6w2ShV6y7bw.png")

        links = []

        for pkg_info_heading, pkg_info in search_pypl.items():

            if pkg_info != '':  # Validating if package field is not a bank string
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

    async def search_pypl(self, package_name: str) -> Dict[str, Union[str, int]]:
        """Collects information from pypi."""
        async with self.bot.http_session.get(package_url.format(package_name=package_name)) as response:

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
    async def pypl(self, ctx: commands.Context, package_name: str) -> None:
        """Provides information about pypi packages by taking package name as input."""
        final_result = await self.search_pypl(package_name=package_name)
        final_embed = self.embed_builder(search_pypl=final_result)
        await ctx.send(embed=final_embed)


def setup(bot: Bot) -> None:
    """Load the Package cog."""
    bot.add_cog(Package(bot))
