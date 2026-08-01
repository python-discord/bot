from datetime import UTC, datetime, timedelta
from typing import TypedDict
from rapidfuzz import process

from discord import Colour, Embed, app_commands, Interaction
from discord.ext.commands import Cog, Context, command

from bot.bot import Bot
from bot.log import get_logger
from bot.utils.messages import send_or_reply

log = get_logger(__name__)

ICON_URL = "https://www.python.org/static/opengraph-icon-200x200.png"
PEP_API_URL = "https://peps.python.org/api/peps.json"


class PEPInfo(TypedDict):
    """
    Useful subset of the PEP API response.

    Full structure documented at https://peps.python.org/api/
    """

    number: int
    title: str
    url: str
    status: str
    python_version: str | None
    created: str
    type: str


class PythonEnhancementProposals(Cog):
    """Cog for displaying information about PEPs."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.peps: dict[int, PEPInfo] = {}
        self.last_refreshed_peps: datetime | None = None

    async def refresh_pep_data(self) -> None:
        """Refresh PEP data."""
        # Putting this first should prevent any race conditions
        self.last_refreshed_peps = datetime.now(tz=UTC)

        log.trace("Started refreshing PEP data.")
        async with self.bot.http_session.get(PEP_API_URL) as resp:
            if resp.status != 200:
                log.warning("Fetching PEP data from PEP API failed with code %s", resp.status)
                return
            listing = await resp.json()

        for pep_num, pep_info in listing.items():
            self.peps[int(pep_num)] = pep_info

        log.info("Successfully refreshed PEP data.")

    def generate_pep_embed(self, pep: PEPInfo) -> Embed:
        """Generate PEP embed."""
        embed = Embed(
            title=f"**PEP {pep['number']} - {pep['title']}**",
            url=pep["url"],
        )
        embed.set_thumbnail(url=ICON_URL)

        fields_to_check = ("status", "python_version", "created", "type")
        for field_name in fields_to_check:
            if field_value := pep.get(field_name):
                field_name = field_name.replace("_", " ").title()
                embed.add_field(name=field_name, value=field_value)

        return embed

    async def get_pep_embed(self, pep_number: int) -> Embed:
        if self.last_refreshed_peps is None or (
            (self.last_refreshed_peps + timedelta(hours=1)) <= datetime.now(tz=UTC) and len(str(pep_number)) < 5
        ):
            await self.refresh_pep_data()

        if pep := self.peps.get(pep_number):
            embed = self.generate_pep_embed(pep)
        else:
            log.trace(f"PEP {pep_number} was not found")
            embed = Embed(
                title="PEP not found",
                description=f"PEP {pep_number} does not exist.",
                colour=Colour.red(),
            )
        return embed

    @command(name="pep", aliases=("get_pep", "p"))
    async def pep_command(self, ctx: Context, pep_number: int) -> None:
        """Fetches information about a PEP and sends it to the channel."""
        # Refresh the PEP data up to every hour, as e.g. the PEP status might have changed.
        embed = await self.get_pep_embed(pep_number)
        await send_or_reply(ctx, embed)

    @app_commands.command(name="pep")
    @app_commands.guild_only()
    @app_commands.describe(pep_number="The pep number or the autocompleted pep")
    async def pep_slash_command(self, interaction: Interaction, pep_number: int) -> bool:
        embed = await self.get_pep_embed(pep_number)
        await interaction.response.send_message(embed=embed)

    @pep_slash_command.autocomplete("pep_number")
    async def pep_slash_command_autocomplete(self, interaction: Interaction, current: str) -> list[app_commands.Choice]:
        if self.last_refreshed_peps is None:
            await self.refresh_pep_data()

        choices = {pep_id: pep_info["title"] for pep_id, pep_info in self.peps.items()}

        # list[('pep_title', similarity, pep_number)]
        result = process.extract(query=current, choices=choices, limit=10)
        return [app_commands.Choice(name=f"{pep[2]} - {pep[0]}", value=pep[2]) for pep in result]


async def setup(bot: Bot) -> None:
    """Load the PEP cog."""
    await bot.add_cog(PythonEnhancementProposals(bot))
