import logging

from aiohttp import ClientSession
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
        
        self.base_pep_url = "https://www.python.org/dev/peps/pep-"
        self.http_session = ClientSession()

    @command(name="pep()", aliases=["peps", "get_pep"])
    @with_role(VERIFIED_ROLE)
    async def pep_search(self, ctx: Context, pep_number: str):
        """
        Fetches information about a PEP and sends it to the user
        """
        pep_url = f"{self.base_pep_url}{str(pep_number.zfill(4))}"

        async with self.http_session.get(pep_url) as resp:
            print(await resp.status())


def setup(bot):
    bot.add_cog(Utils(bot))
    log.info("Utils cog loaded")
        
    