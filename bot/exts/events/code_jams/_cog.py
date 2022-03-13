import asyncio
import csv
import typing as t
from collections import defaultdict

import disnake
from disnake import Colour, Embed, Guild, Member
from disnake.ext import commands

from bot.bot import Bot
from bot.constants import Emojis, Roles
from bot.exts.events.code_jams import _channels
from bot.log import get_logger
from bot.utils.members import get_or_fetch_member
from bot.utils.services import send_to_paste_service

log = get_logger(__name__)

TEAM_LEADERS_COLOUR = 0x11806a
DELETION_REACTION = "\U0001f4a5"


class CodeJams(commands.Cog):
    """Manages the code-jam related parts of our server."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.group(aliases=("cj", "jam"))
    @commands.has_any_role(Roles.admins)
    async def codejam(self, ctx: commands.Context) -> None:
        """A Group of commands for managing Code Jams."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @codejam.command()
    async def create(self, ctx: commands.Context, csv_file: t.Optional[str] = None) -> None:
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
                member = await get_or_fetch_member(ctx.guild, int(row["Team Member Discord ID"]))

                if member is None:
                    log.trace(f"Got an invalid member ID: {row['Team Member Discord ID']}")
                    continue

                teams[row["Team Name"]].append((member, row["Team Leader"].upper() == "Y"))

            team_leaders = await ctx.guild.create_role(name="Code Jam Team Leaders", colour=TEAM_LEADERS_COLOUR)

            for team_name, team_members in teams.items():
                await _channels.create_team_channel(ctx.guild, team_name, team_members, team_leaders)

            await _channels.create_team_leader_channel(ctx.guild, team_leaders)
            await ctx.send(f"{Emojis.check_mark} Created Code Jam with {len(teams)} teams.")

    @codejam.command()
    @commands.has_any_role(Roles.admins)
    async def end(self, ctx: commands.Context) -> None:
        """
        Delete all code jam channels.

        A confirmation message is displayed with the categories and channels to be deleted.. Pressing the added reaction
        deletes those channels.
        """
        def predicate_deletion_emoji_reaction(reaction: disnake.Reaction, user: disnake.User) -> bool:
            """Return True if the reaction :boom: was added by the context message author on this message."""
            return (
                reaction.message.id == message.id
                and user.id == ctx.author.id
                and str(reaction) == DELETION_REACTION
            )

        # A copy of the list of channels is stored. This is to make sure that we delete precisely the channels displayed
        # in the confirmation message.
        categories = self.jam_categories(ctx.guild)
        category_channels = {category: category.channels.copy() for category in categories}

        confirmation_message = await self._build_confirmation_message(category_channels)
        message = await ctx.send(confirmation_message)
        await message.add_reaction(DELETION_REACTION)
        try:
            await self.bot.wait_for(
                'reaction_add',
                check=predicate_deletion_emoji_reaction,
                timeout=10
            )

        except asyncio.TimeoutError:
            await message.clear_reaction(DELETION_REACTION)
            await ctx.send("Command timed out.", reference=message)
            return

        else:
            await message.clear_reaction(DELETION_REACTION)
            for category, channels in category_channels.items():
                for channel in channels:
                    await channel.delete(reason="Code jam ended.")
                await category.delete(reason="Code jam ended.")

            await message.add_reaction(Emojis.check_mark)

    @staticmethod
    async def _build_confirmation_message(
        categories: dict[disnake.CategoryChannel, list[disnake.abc.GuildChannel]]
    ) -> str:
        """Sends details of the channels to be deleted to the pasting service, and formats the confirmation message."""
        def channel_repr(channel: disnake.abc.GuildChannel) -> str:
            """Formats the channel name and ID and a readable format."""
            return f"{channel.name} ({channel.id})"

        def format_category_info(category: disnake.CategoryChannel, channels: list[disnake.abc.GuildChannel]) -> str:
            """Displays the category and the channels within it in a readable format."""
            return f"{channel_repr(category)}:\n" + "\n".join("  - " + channel_repr(channel) for channel in channels)

        deletion_details = "\n\n".join(
            format_category_info(category, channels) for category, channels in categories.items()
        )

        url = await send_to_paste_service(deletion_details)
        if url is None:
            url = "**Unable to send deletion details to the pasting service.**"

        return f"Are you sure you want to delete all code jam channels?\n\nThe channels to be deleted: {url}"

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
            colour=Colour.og_blurple()
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
            overwrite=disnake.PermissionOverwrite(read_messages=True),
            reason=f"Participant moved from {old_team_channel.name}"
        )

        await ctx.send(
            f"Participant moved from `{self.team_name(old_team_channel)}` to `{self.team_name(new_team_channel)}`."
        )

    @codejam.command()
    @commands.has_any_role(Roles.admins)
    async def remove(self, ctx: commands.Context, member: Member) -> None:
        """Remove the participant from their team. Does not remove the participants or leader roles."""
        channel = self.team_channel(ctx.guild, member)
        if not channel:
            await ctx.send(":x: I can't find the team channel for this member.")
            return

        await channel.set_permissions(
            member,
            overwrite=None,
            reason=f"Participant removed from the team  {self.team_name(channel)}."
        )
        await ctx.send(f"Removed the participant from `{self.team_name(channel)}`.")

    @staticmethod
    def jam_categories(guild: Guild) -> list[disnake.CategoryChannel]:
        """Get all the code jam team categories."""
        return [category for category in guild.categories if category.name == _channels.CATEGORY_NAME]

    @staticmethod
    def team_channel(guild: Guild, criterion: t.Union[str, Member]) -> t.Optional[disnake.TextChannel]:
        """Get a team channel through either a participant or the team name."""
        for category in CodeJams.jam_categories(guild):
            for channel in category.channels:
                if isinstance(channel, disnake.TextChannel):
                    if (
                        # If it's a string.
                        criterion == channel.name or criterion == CodeJams.team_name(channel)
                        # If it's a member.
                        or criterion in channel.overwrites
                    ):
                        return channel

    @staticmethod
    def team_name(channel: disnake.TextChannel) -> str:
        """Retrieves the team name from the given channel."""
        return channel.name.replace("-", " ").title()
