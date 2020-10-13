import logging
from typing import Dict, Union

from discord.ext import commands

from bot.bot import Bot


log = logging.getLogger(__name__)

package_url = "https://pypi.org/pypi/{package_name}/json"
pypl_url = "pip install {name_of_package}"


class Package(commands.Cog):
    """Provides Information about package hosted at pypl."""

    def __init__(self, bot: Bot):
        self.bot = bot

    async def search_pypl(self, package_name: str) -> Dict[str, Union[str, int]]:
        """Collects information from pypl."""
        async with self.bot.http_session.get(package_url.format(package_name=package_name)) as response:
            a = await response.json()
            info = {"pkg_name": a["info"]["name"],
                    "summary": a["info"]["summary"],
                    "author": a["info"]["author"],
                    "maintainer": a["info"]["maintainer"],
                    "project_url": a["info"]["project_url"],
                    "home_page": a["info"]["home_page"],
                    "requires_python": a["info"]["requires_python"],
                    "version": a["info"]["version"],
                    "license": a["info"]["license"],
                    "monthly_download": a["info"]["downloads"]["last_month"]
                    }
        return info

    @commands.command(name="pypl")
    async def pypl(self, ctx: commands.Context, package_name: str) -> None:
        """Provdies information about pypl packages by taking package name as input."""
        final_result = await self.search_pypl(package_name=package_name)
        await ctx.send(final_result)


def setup(bot: Bot) -> None:
    """Load the Package cog."""
    bot.add_cog(Package(bot))
