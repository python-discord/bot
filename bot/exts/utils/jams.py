import logging
import typing as t

from discord import CategoryChannel, Guild, Member, PermissionOverwrite, Role
from discord.ext import commands
from more_itertools import unique_everseen

from bot.bot import Bot
from bot.constants import Roles

log = logging.getLogger(__name__)

MAX_CHANNELS = 50
CATEGORY_NAME = "Code Jam"


class CodeJams(commands.Cog):
    """Manages the code-jam related parts of our server."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.command()
    @commands.has_any_role(Roles.admins)
    async def createteam(self, ctx: commands.Context, team_name: str, members: commands.Greedy[Member]) -> None:
        """
        Create team channels (voice and text) in the Code Jams category, assign roles, and add overwrites for the team.

        The first user passed will always be the team leader.
        """
        # Ignore duplicate members
        members = list(unique_everseen(members))

        # We had a little issue during Code Jam 4 here, the greedy converter did it's job
        # and ignored anything which wasn't a valid argument which left us with teams of
        # two members or at some times even 1 member. This fixes that by checking that there
        # are always 3 members in the members list.
        if len(members) < 3:
            await ctx.send(
                ":no_entry_sign: One of your arguments was invalid\n"
                f"There must be a minimum of 3 valid members in your team. Found: {len(members)}"
                " members"
            )
            return

        team_channel = await self.create_channels(ctx.guild, team_name, members)
        await self.add_roles(ctx.guild, members)

        await ctx.send(
            f":ok_hand: Team created: {team_channel}\n"
            f"**Team Leader:** {members[0].mention}\n"
            f"**Team Members:** {' '.join(member.mention for member in members[1:])}"
        )

    async def get_category(self, guild: Guild) -> CategoryChannel:
        """
        Return a code jam category.

        If all categories are full or none exist, create a new category.
        """
        for category in guild.categories:
            # Need 2 available spaces: one for the text channel and one for voice.
            if category.name == CATEGORY_NAME and MAX_CHANNELS - len(category.channels) >= 2:
                return category

        return await self.create_category(guild)

    @staticmethod
    async def create_category(guild: Guild) -> CategoryChannel:
        """Create a new code jam category and return it."""
        log.info("Creating a new code jam category.")

        category_overwrites = {
            guild.default_role: PermissionOverwrite(read_messages=False),
            guild.me: PermissionOverwrite(read_messages=True)
        }

        return await guild.create_category_channel(
            CATEGORY_NAME,
            overwrites=category_overwrites,
            reason="It's code jam time!"
        )

    @staticmethod
    def get_overwrites(members: t.List[Member], guild: Guild) -> t.Dict[t.Union[Member, Role], PermissionOverwrite]:
        """Get code jam team channels permission overwrites."""
        # First member is always the team leader
        team_channel_overwrites = {
            members[0]: PermissionOverwrite(
                manage_messages=True,
                read_messages=True,
                manage_webhooks=True,
                connect=True
            ),
            guild.default_role: PermissionOverwrite(read_messages=False, connect=False),
        }

        # Rest of members should just have read_messages
        for member in members[1:]:
            team_channel_overwrites[member] = PermissionOverwrite(
                read_messages=True,
                connect=True
            )

        return team_channel_overwrites

    async def create_channels(self, guild: Guild, team_name: str, members: t.List[Member]) -> str:
        """Create team text and voice channels. Return the mention for the text channel."""
        # Get permission overwrites and category
        team_channel_overwrites = self.get_overwrites(members, guild)
        code_jam_category = await self.get_category(guild)

        # Create a text channel for the team
        team_channel = await guild.create_text_channel(
            team_name,
            overwrites=team_channel_overwrites,
            category=code_jam_category
        )

        # Create a voice channel for the team
        team_voice_name = " ".join(team_name.split("-")).title()

        await guild.create_voice_channel(
            team_voice_name,
            overwrites=team_channel_overwrites,
            category=code_jam_category
        )

        return team_channel.mention

    @staticmethod
    async def add_roles(guild: Guild, members: t.List[Member]) -> None:
        """Assign team leader and jammer roles."""
        # Assign team leader role
        await members[0].add_roles(guild.get_role(Roles.team_leaders))

        # Assign rest of roles
        jammer_role = guild.get_role(Roles.jammers)
        for member in members:
            await member.add_roles(jammer_role)


def setup(bot: Bot) -> None:
    """Load the CodeJams cog."""
    bot.add_cog(CodeJams(bot))
