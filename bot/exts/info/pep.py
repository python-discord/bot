from datetime import UTC, datetime, timedelta
from typing import TypedDict

from discord import Colour, Embed, Interaction, app_commands
from discord.ext.commands import Cog, Context, command
from rapidfuzz import process

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
        self.pep_autocomplete_choices: dict[int, str] = {}
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

        for pep_num_str, pep_info in listing.items():
            pep_num = int(pep_num_str)
            self.peps[pep_num] = pep_info
            self.pep_autocomplete_choices[pep_num] = f"{pep_num} - {pep_info["title"]}"

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

    async def refresh_pep_data_if_needed(self, *, pep_number: int | None = None) -> None:
        """Refreshes the PEP data only when a certain criteria is met."""
        if self.last_refreshed_peps is None or (self.last_refreshed_peps + timedelta(hours=1)) <= datetime.now(tz=UTC):
            if pep_number is not None and len(str(pep_number)) >= 5:
                return
            await self.refresh_pep_data()

    async def get_pep_embed(self, pep_number: int) -> Embed:
        """Refreshes the PEP data if needed and generates the PEP embed."""
        await self.refresh_pep_data_if_needed(pep_number=pep_number)

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
    @app_commands.describe(pep_number="PEP number or title")
    async def pep_slash_command(self, interaction: Interaction, pep_number: int) -> None:
        """Fetches information about a PEP and sends it to the channel."""
        embed = await self.get_pep_embed(pep_number)
        await interaction.response.send_message(embed=embed)

    @pep_slash_command.autocomplete("pep_number")
    async def pep_slash_command_autocomplete(self, interaction: Interaction, query: str) -> list[app_commands.Choice]:
        """Returns a list of PEPs that matches `query`."""
        await self.refresh_pep_data_if_needed()

        if len(query) < 5 and query.isdigit():
            pep_num = int(query)
            pep_title = self.pep_autocomplete_choices.get(pep_num)
            if pep_title is not None:
                return [app_commands.Choice(name=pep_title, value=pep_num)]
            return []

        # list[('pep_num - pep_title', similarity, pep_number)]
        result = process.extract(query=query, choices=self.pep_autocomplete_choices, limit=10, processor=str.casefold)
        return [app_commands.Choice(name=pep[0], value=pep[2]) for pep in result]


async def setup(bot: Bot) -> None:
    """Load the PEP cog."""
    await bot.add_cog(PythonEnhancementProposals(bot))
