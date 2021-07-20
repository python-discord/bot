import csv
import logging
import typing as t
from collections import defaultdict

import discord
from discord.ext import commands

from bot.bot import Bot
from bot.constants import Categories, Channels, Emojis, Roles

log = logging.getLogger(__name__)

MAX_CHANNELS = 50
CATEGORY_NAME = "Code Jam"
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
                await self.create_team_channel(ctx.guild, team_name, members, team_leaders)

            await self.create_team_leader_channel(ctx.guild, team_leaders)
            await ctx.send(f"{Emojis.check_mark} Created Code Jam with {len(teams)} teams.")

    async def get_category(self, guild: discord.Guild) -> discord.CategoryChannel:
        """
        Return a code jam category.

        If all categories are full or none exist, create a new category.
        """
        for category in guild.categories:
            if category.name == CATEGORY_NAME and len(category.channels) < MAX_CHANNELS:
                return category

        return await self.create_category(guild)

    async def create_category(self, guild: discord.Guild) -> discord.CategoryChannel:
        """Create a new code jam category and return it."""
        log.info("Creating a new code jam category.")

        category_overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }

        category = await guild.create_category_channel(
            CATEGORY_NAME,
            overwrites=category_overwrites,
            reason="It's code jam time!"
        )

        await self.send_status_update(
            guild, f"Created a new category with the ID {category.id} for this Code Jam's team channels."
        )

        return category

    @staticmethod
    def get_overwrites(
        members: list[tuple[discord.Member, bool]],
        guild: discord.Guild,
    ) -> dict[t.Union[discord.Member, discord.Role], discord.PermissionOverwrite]:
        """Get code jam team channels permission overwrites."""
        team_channel_overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.get_role(Roles.code_jam_event_team): discord.PermissionOverwrite(read_messages=True)
        }

        for member, _ in members:
            team_channel_overwrites[member] = discord.PermissionOverwrite(
                read_messages=True
            )

        return team_channel_overwrites

    async def create_team_channel(
        self,
        guild: discord.Guild,
        team_name: str,
        members: list[tuple[discord.Member, bool]],
        team_leaders: discord.Role
    ) -> None:
        """Create the team's text channel."""
        await self.add_team_leader_roles(members, team_leaders)

        # Get permission overwrites and category
        team_channel_overwrites = self.get_overwrites(members, guild)
        code_jam_category = await self.get_category(guild)

        # Create a text channel for the team
        await code_jam_category.create_text_channel(
            team_name,
            overwrites=team_channel_overwrites,
        )

    async def create_team_leader_channel(self, guild: discord.Guild, team_leaders: discord.Role) -> None:
        """Create the Team Leader Chat channel for the Code Jam team leaders."""
        category: discord.CategoryChannel = guild.get_channel(Categories.summer_code_jam)

        team_leaders_chat = await category.create_text_channel(
            name="team-leaders-chat",
            overwrites={
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                team_leaders: discord.PermissionOverwrite(read_messages=True)
            }
        )

        await self.send_status_update(guild, f"Created {team_leaders_chat.mention} in the {category} category.")

    async def send_status_update(self, guild: discord.Guild, message: str) -> None:
        """Inform the events lead with a status update when the command is ran."""
        channel: discord.TextChannel = guild.get_channel(Channels.code_jam_planning)

        await channel.send(f"<@&{Roles.events_lead}>\n\n{message}")

    @staticmethod
    async def add_team_leader_roles(members: list[tuple[discord.Member, bool]], team_leaders: discord.Role) -> None:
        """Assign team leader role, the jammer role and their team role."""
        for member, is_leader in members:
            if is_leader:
                await member.add_roles(team_leaders)


def setup(bot: Bot) -> None:
    """Load the CodeJams cog."""
    bot.add_cog(CodeJams(bot))
