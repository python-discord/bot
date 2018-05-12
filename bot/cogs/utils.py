from email.parser import HeaderParser
import logging
from io import StringIO


from discord import Embed
from discord.ext.commands import AutoShardedBot, Context, command

from bot.constants import VERIFIED_ROLE
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
    @with_role(VERIFIED_ROLE)
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

            # Remove unnecessary information.
            del pep_header["Content-Type"]
            del pep_header["PEP"]
            for key in pep_header:
                if "$" in pep_header[key] or not pep_header[key]:
                    del pep_header[key]

            pep_embed = Embed(title=f"PEP {pep_number}")
            pep_embed.add_field(name="Link", value=f"{self.base_pep_url}{pep_number.zfill(4)}")
            for key in pep_header:
                pep_embed.add_field(name=key, value=pep_header[key], inline=False)

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
