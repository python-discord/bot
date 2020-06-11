import logging
import typing as t

from discord import CategoryChannel, Member, PermissionOverwrite, utils
from discord.ext import commands
from more_itertools import unique_everseen

from bot.bot import Bot
from bot.constants import Roles
from bot.decorators import with_role

log = logging.getLogger(__name__)


class CodeJams(commands.Cog):
    """Manages the code-jam related parts of our server."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.command()
    @with_role(Roles.admins)
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

        team_channel = await self.create_channels(ctx, team_name, members)
        await self.add_roles(ctx, members)

        await ctx.send(
            f":ok_hand: Team created: {team_channel}\n"
            f"**Team Leader:** {members[0].mention}\n"
            f"**Team Members:** {' '.join(member.mention for member in members[1:])}"
        )

    async def get_category(self, ctx: commands.Context) -> CategoryChannel:
        """Create Code Jam category when this don't exist and return this."""
        code_jam_category = utils.get(ctx.guild.categories, name="Code Jam")

        if code_jam_category is None:
            log.info("Code Jam category not found, creating it.")

            category_overwrites = {
                ctx.guild.default_role: PermissionOverwrite(read_messages=False),
                ctx.guild.me: PermissionOverwrite(read_messages=True)
            }

            code_jam_category = await ctx.guild.create_category_channel(
                "Code Jam",
                overwrites=category_overwrites,
                reason="It's code jam time!"
            )

        return code_jam_category

    def get_overwrites(self, members: t.List[Member], ctx: commands.Context) -> t.Dict[Member, PermissionOverwrite]:
        """Get Code Jam team channels permission overwrites."""
        # First member is always the team leader
        team_channel_overwrites = {
            members[0]: PermissionOverwrite(
                manage_messages=True,
                read_messages=True,
                manage_webhooks=True,
                connect=True
            ),
            ctx.guild.default_role: PermissionOverwrite(read_messages=False, connect=False),
            ctx.guild.get_role(Roles.verified): PermissionOverwrite(
                read_messages=False,
                connect=False
            )
        }

        # Rest of members should just have read_messages
        for member in members[1:]:
            team_channel_overwrites[member] = PermissionOverwrite(
                read_messages=True,
                connect=True
            )

        return team_channel_overwrites

    async def create_channels(self, ctx: commands.Context, team_name: str, members: t.List[Member]) -> str:
        """Create team text and voice channel. Return name of text channel."""
        # Get permission overwrites and category
        team_channel_overwrites = self.get_overwrites(members, ctx)
        code_jam_category = await self.get_category(ctx)

        # Create a text channel for the team
        team_channel = await ctx.guild.create_text_channel(
            team_name,
            overwrites=team_channel_overwrites,
            category=code_jam_category
        )

        # Create a voice channel for the team
        team_voice_name = " ".join(team_name.split("-")).title()

        await ctx.guild.create_voice_channel(
            team_voice_name,
            overwrites=team_channel_overwrites,
            category=code_jam_category
        )

        return team_channel.mention

    async def add_roles(self, ctx: commands.Context, members: t.List[Member]) -> None:
        """Assign team leader and jammer roles."""
        # Assign team leader role
        await members[0].add_roles(ctx.guild.get_role(Roles.team_leaders))

        # Assign rest of roles
        jammer_role = ctx.guild.get_role(Roles.jammers)
        for member in members:
            await member.add_roles(jammer_role)


def setup(bot: Bot) -> None:
    """Load the CodeJams cog."""
    bot.add_cog(CodeJams(bot))
