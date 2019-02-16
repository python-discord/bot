import logging

from discord import Member, PermissionOverwrite, utils
from discord.ext import commands

from bot.constants import Roles
from bot.decorators import with_role

log = logging.getLogger(__name__)


class CodeJams:
    """
    A cog for managing the code-jam related parts of our server
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command()
    @with_role(Roles.admin)
    async def createteam(
        self, ctx: commands.Context,
        team_name: str, members: commands.Greedy[Member]
    ):
        """
        Create a team channel in the Code Jams category, assign roles and then add
        overwrites for the team.

        The first user passed will always be the team leader.
        """
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

        # First member is always the team leader
        team_channel_overwrites = {
            members[0]: PermissionOverwrite(
                manage_messages=True,
                read_messages=True,
                manage_webhooks=True
            ),
            ctx.guild.default_role: PermissionOverwrite(read_messages=False),
            ctx.guild.get_role(Roles.developer): PermissionOverwrite(read_messages=False)
        }

        # Rest of members should just have read_messages
        for member in members[1:]:
            team_channel_overwrites[member] = PermissionOverwrite(read_messages=True)

        # Create a channel for the team
        team_channel = await ctx.guild.create_text_channel(
            team_name,
            overwrites=team_channel_overwrites,
            category=code_jam_category
        )

        # Assign team leader role
        await members[0].add_roles(ctx.guild.get_role(Roles.team_leader))

        # Assign rest of roles
        jammer_role = ctx.guild.get_role(Roles.jammer)
        for member in members:
            await member.add_roles(jammer_role)

        await ctx.send(f":ok_hand: Team created: {team_channel.mention}")


def setup(bot):
    bot.add_cog(CodeJams(bot))
    log.info("Cog loaded: CodeJams")
