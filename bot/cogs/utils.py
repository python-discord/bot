import logging
from email.parser import HeaderParser
from io import StringIO


from discord import Embed
from discord.ext.commands import AutoShardedBot, Context, command

from bot.constants import Roles
from bot.decorators import with_role

log = logging.getLogger(__name__)


class Utils:
    """
    Helpful commands
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

        self.base_pep_url = "http://www.python.org/dev/peps/pep-"
        self.base_github_pep_url = "https://raw.githubusercontent.com/python/peps/master/pep-"

    @command(name="pep()", aliases=["pep", "get_pep"])
    @with_role(Roles.verified)
    async def pep_search(self, ctx: Context, pep_number: str):
        """
        Fetches information about a PEP and sends it to the user
        """
        # Attempt to fetch the PEP from Github.
        pep_url = f"{self.base_github_pep_url}{pep_number.zfill(4)}.txt"
        log.trace(f"Requesting PEP {pep_number} with {pep_url}")
        response = await self.bot.http_session.get(pep_url)

        if response.status == 200:
            log.trace("PEP found")

            pep_content = await response.text()

            # Taken from https://github.com/python/peps/blob/master/pep0/pep.py#L179
            pep_header = HeaderParser().parse(StringIO(pep_content))

            # Assemble the embed
            pep_embed = Embed(
                title=f"**PEP {pep_number} - {pep_header['Title']}**",
                description=f"[Link]({self.base_pep_url+pep_number.zfill(4)})",
            )

            pep_embed.set_thumbnail(url="https://www.python.org/static/opengraph-icon-200x200.png")

            # Add the interesting information
            if "Status" in pep_header:
                pep_embed.add_field(name="Status", value=pep_header["Status"])
            if "Python-Version" in pep_header:
                pep_embed.add_field(name="Python-Version", value=pep_header["Python-Version"])
            if "Created" in pep_header:
                pep_embed.add_field(name="Created", value=pep_header["Created"])
            if "Type" in pep_header:
                pep_embed.add_field(name="Type", value=pep_header["Type"])

        elif response.status == 404:
            log.trace("PEP was not found")
            not_found = f"PEP {pep_number} is not an existing one"
            pep_embed = Embed(title="PEP not found", description=not_found)

        else:
            log.trace(f"HTTP error {response.status} during request of PEP")
            return

        await ctx.message.channel.send(embed=pep_embed)


def setup(bot):
    bot.add_cog(Utils(bot))
    log.info("Utils cog loaded")
