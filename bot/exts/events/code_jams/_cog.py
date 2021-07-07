import csv
import logging
import typing as t
from collections import defaultdict

from discord.ext import commands

from bot.bot import Bot
from bot.constants import Emojis, Roles
from bot.exts.events.code_jams import _channels

log = logging.getLogger(__name__)

TEAM_LEADERS_COLOUR = 0x11806a


class CodeJams(commands.Cog):
    """Manages the code-jam related parts of our server."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.group()
    @commands.has_any_role(Roles.admins)
    async def codejam(self, ctx: commands.Context) -> None:
        """A Group of commands for managing Code Jams."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @codejam.command()
    async def create(self, ctx: commands.Context, csv_file: t.Optional[str]) -> None:
        """
        Create code-jam teams from a CSV file or a link to one, specifying the team names, leaders and members.

        The CSV file must have 3 columns: 'Team Name', 'Team Member Discord ID', and 'Team Leader'.

        This will create the text channels for the teams, and give the team leaders their roles.
        """
        async with ctx.typing():
            if csv_file:
                async with self.bot.http_session.get(csv_file) as response:
                    if response.status != 200:
                        await ctx.send(f"Got a bad response from the URL: {response.status}")
                        return

                    csv_file = await response.text()

            elif ctx.message.attachments:
                csv_file = (await ctx.message.attachments[0].read()).decode("utf8")
            else:
                raise commands.BadArgument("You must include either a CSV file or a link to one.")

            teams = defaultdict(list)
            reader = csv.DictReader(csv_file.splitlines())

            for row in reader:
                member = ctx.guild.get_member(int(row["Team Member Discord ID"]))

                if member is None:
                    log.trace(f"Got an invalid member ID: {row['Team Member Discord ID']}")
                    continue

                teams[row["Team Name"]].append((member, row["Team Leader"].upper() == "Y"))

            team_leaders = await ctx.guild.create_role(name="Code Jam Team Leaders", colour=TEAM_LEADERS_COLOUR)

            for team_name, members in teams.items():
                await _channels.create_team_channel(ctx.guild, team_name, members, team_leaders)

            await _channels.create_team_leader_channel(ctx.guild, team_leaders)
            await ctx.send(f"{Emojis.check_mark} Created Code Jam with {len(teams)} teams.")
