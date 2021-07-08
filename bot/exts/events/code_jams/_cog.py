import csv
import logging
import typing as t
from collections import defaultdict

import discord
from discord import Colour, Embed, Guild, Member
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

        self.end_counter = 0

    @commands.group(aliases=("cj", "jam"))
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

    @codejam.command()
    @commands.has_any_role(Roles.admins)
    async def end(self, ctx: commands.Context) -> None:
        """
        Deletes all code jam channels.

        Call it three times while spinning around for it all to end.
        """
        self.end_counter += 1
        if self.end_counter == 1:
            await ctx.send("Are you sure about that?")
            return
        if self.end_counter == 2:
            await ctx.send("Are you *really really* sure about that?")
            return

        self.end_counter = 0

        for category in self.jam_categories(ctx.guild):
            for channel in category.channels:
                await channel.delete(reason="Code jam ended.")
            await category.delete(reason="Code jam ended.")

        await ctx.message.add_reaction(Emojis.check_mark)

    @codejam.command()
    @commands.has_any_role(Roles.admins, Roles.code_jam_event_team)
    async def info(self, ctx: commands.Context, member: Member) -> None:
        """
        Send an info embed about the member with the team they're in.

        The team is found by searching the permissions of the team channels.
        """
        channel = self.team_channel(ctx.guild, member)
        if not channel:
            await ctx.send(":x: I can't find the team channel for this member.")
            return

        embed = Embed(
            title=str(member),
            colour=Colour.blurple()
        )
        embed.add_field(name="Team", value=self.team_name(channel), inline=True)

        await ctx.send(embed=embed)

    @codejam.command()
    @commands.has_any_role(Roles.admins)
    async def move(self, ctx: commands.Context, member: Member, new_team_name: str) -> None:
        """Move participant from one team to another by changing the user's permissions for the relevant channels."""
        old_team_channel = self.team_channel(ctx.guild, member)
        if not old_team_channel:
            await ctx.send(":x: I can't find the team channel for this member.")
            return

        if old_team_channel.name == new_team_name or self.team_name(old_team_channel) == new_team_name:
            await ctx.send(f"`{member}` is already in `{new_team_name}`.")
            return

        new_team_channel = self.team_channel(ctx.guild, new_team_name)
        if not new_team_channel:
            await ctx.send(f":x: I can't find a team channel named `{new_team_name}`.")
            return

        await old_team_channel.set_permissions(member, overwrite=None, reason=f"Participant moved to {new_team_name}")
        await new_team_channel.set_permissions(
            member,
            overwrite=discord.PermissionOverwrite(read_messages=True),
            reason=f"Participant moved from {old_team_channel.name}"
        )

        await ctx.send(
            f"Participant moved from `{self.team_name(old_team_channel)}` to `{self.team_name(new_team_channel)}`."
        )

    @codejam.command()
    @commands.has_any_role(Roles.admins)
    async def remove(self, ctx: commands.Context, member: Member) -> None:
        """Removes the participant from their team. Does not remove the participants or leader roles."""
        channel = self.team_channel(ctx.guild, member)
        if not channel:
            await ctx.send(":x: I can't find the team channel for this member.")
            return

        await channel.set_permissions(member, overwrite=None, reason="Participant removed from the team.")
        await ctx.send(f"Removed the participant from `{self.team_name(channel)}`.")

    @staticmethod
    def jam_categories(guild: Guild) -> list[discord.CategoryChannel]:
        """Get all the code jam team categories."""
        return [category for category in guild.categories if category.name == _channels.CATEGORY_NAME]

    @staticmethod
    def team_channel(guild: Guild, criterion: t.Union[str, Member]) -> t.Optional[discord.TextChannel]:
        """Get a team channel through either a participant or the team name."""
        for category in CodeJams.jam_categories(guild):
            for channel in category.channels:
                if isinstance(channel, discord.TextChannel):
                    if (
                        # If it's a string.
                        criterion == channel.name or criterion == CodeJams.team_name(channel)
                        # If it's a member.
                        or criterion in channel.overwrites
                    ):
                        return channel

    @staticmethod
    def team_name(channel: discord.TextChannel) -> str:
        """Retrieves the team name from the given channel."""
        return channel.name.replace("-", " ").title()
