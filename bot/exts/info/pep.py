from datetime import UTC, datetime, timedelta
from typing import Optional

from discord import Colour, Embed
from discord.ext.commands import Cog, Context, command
from pydis_core.utils.caching import AsyncCache

from bot.bot import Bot
from bot.log import get_logger

log = get_logger(__name__)

ICON_URL = "https://www.python.org/static/opengraph-icon-200x200.png"
PEP_API_URL = "https://peps.python.org/api/peps.json"


class PythonEnhancementProposals(Cog):
    """Cog for displaying information about PEPs."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.peps: dict[int, dict[str, Optional[str]]] = {}
        self.last_refreshed_peps: Optional[datetime] = None

    async def refresh_pep_data(self) -> None:
        """Refresh PEP data."""
        # Putting this first should prevent any race conditions
        self.last_refreshed_peps = datetime.now(tz=UTC)

        # Wait until HTTP client is available
        await self.bot.wait_until_ready()

        log.trace("Started refreshing PEP data.")
        async with self.bot.http_session.get(PEP_API_URL) as resp:
            if resp.status != 200:
                log.warning(
                    f"Fetching PEP data from PEP API failed with code {resp.status}"
                )
                return
            listing = await resp.json()

        for pep_num, pep_info in listing.items():
            self.peps[int(pep_num)] = pep_info

        log.info("Successfully refreshed PEP data.")

    def generate_pep_embed(self, pep_number: int) -> Embed:
        """Generate PEP embed."""
        pep = self.peps[pep_number]
        embed = Embed(
            title=f"**PEP {pep_number} - {pep['title']}**",
            description=f"[Link]({pep['url']})",
        )
        embed.set_thumbnail(url=ICON_URL)

        fields_to_check = ("status", "python_version", "created", "type")
        for field_name in fields_to_check:
            if field_value := pep.get(field_name):
                field_name = field_name.replace("_", " ").title()
                embed.add_field(name=field_name, value=field_value)

        return embed

    @command(name="pep", aliases=("get_pep", "p"))
    async def pep_command(self, ctx: Context, pep_number: int) -> None:
        """Fetches information about a PEP and sends it to the channel."""
        if (
            self.last_refreshed_peps is None or (
                pep_number not in self.peps
                and (self.last_refreshed_peps + timedelta(minutes=30)) <= datetime.now()
                and len(str(pep_number)) < 5
            )
        ):
            await self.refresh_pep_data()

        if pep_number not in self.peps:
            log.trace(f"PEP {pep_number} was not found")
            embed = Embed(
                title="PEP not found",
                description=f"PEP {pep_number} does not exist.",
                colour=Colour.red(),
            )
        else:
            embed = self.generate_pep_embed(pep_number)

        await ctx.send(embed=embed)


async def setup(bot: Bot) -> None:
    """Load the PEP cog."""
    await bot.add_cog(PythonEnhancementProposals(bot))
