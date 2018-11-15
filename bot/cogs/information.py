import logging
import textwrap

from discord import CategoryChannel, Colour, Embed, Member, TextChannel, VoiceChannel
from discord.ext.commands import Bot, Context, command

from bot.constants import Emojis, Keys, Roles, URLs
from bot.decorators import with_role
from bot.utils.time import time_since

log = logging.getLogger(__name__)

MODERATION_ROLES = Roles.owner, Roles.admin, Roles.moderator


class Information:
    """
    A cog with commands for generating embeds with
    server information, such as server statistics
    and user information.
    """

    def __init__(self, bot: Bot):
        self.bot = bot
        self.headers = {"X-API-Key": Keys.site_api}

    @with_role(*MODERATION_ROLES)
    @command(name="roles")
    async def roles_info(self, ctx: Context):
        """
        Returns a list of all roles and their
        corresponding IDs.
        """

        # Sort the roles alphabetically and remove the @everyone role
        roles = sorted(ctx.guild.roles, key=lambda role: role.name)
        roles = [role for role in roles if role.name != "@everyone"]

        # Build a string
        role_string = ""
        for role in roles:
            role_string += f"`{role.id}` - {role.mention}\n"

        # Build an embed
        embed = Embed(
            title="Role information",
            colour=Colour.blurple(),
            description=role_string
        )

        embed.set_footer(text=f"Total roles: {len(roles)}")

        await ctx.send(embed=embed)

    @command(name="server", aliases=["server_info", "guild", "guild_info"])
    async def server_info(self, ctx: Context):
        """
        Returns an embed full of
        server information.
        """

        created = time_since(ctx.guild.created_at, precision="days")
        features = ", ".join(ctx.guild.features)
        region = ctx.guild.region

        # How many of each type of channel?
        roles = len(ctx.guild.roles)
        channels = ctx.guild.channels
        text_channels = 0
        category_channels = 0
        voice_channels = 0
        for channel in channels:
            if type(channel) == TextChannel:
                text_channels += 1
            elif type(channel) == CategoryChannel:
                category_channels += 1
            elif type(channel) == VoiceChannel:
                voice_channels += 1

        # How many of each user status?
        member_count = ctx.guild.member_count
        members = ctx.guild.members
        online = 0
        dnd = 0
        idle = 0
        offline = 0
        for member in members:
            if str(member.status) == "online":
                online += 1
            elif str(member.status) == "offline":
                offline += 1
            elif str(member.status) == "idle":
                idle += 1
            elif str(member.status) == "dnd":
                dnd += 1

        embed = Embed(
            colour=Colour.blurple(),
            description=textwrap.dedent(f"""
                **Server information**
                Created: {created}
                Voice region: {region}
                Features: {features}

                **Counts**
                Members: {member_count}
                Roles: {roles}
                Text: {text_channels}
                Voice: {voice_channels}
                Channel categories: {category_channels}

                **Members**
                {Emojis.status_online} {online}
                {Emojis.status_idle} {idle}
                {Emojis.status_dnd} {dnd}
                {Emojis.status_offline} {offline}
            """)
        )

        embed.set_thumbnail(url=ctx.guild.icon_url)

        await ctx.send(embed=embed)

    @with_role(*MODERATION_ROLES)
    @command(name="user", aliases=["user_info", "member", "member_info"])
    async def user_info(self, ctx: Context, user: Member = None, hidden: bool = False):
        """
        Returns info about a user.
        """

        # Validates hidden input
        hidden = str(hidden)

        if user is None:
            user = ctx.author

        # User information
        created = time_since(user.created_at, max_units=3)

        name = f"{user.name}#{user.discriminator}"
        if user.nick:
            name = f"{user.nick} ({name})"

        # Member information
        joined = time_since(user.joined_at, precision="days")

        # You're welcome, Volcyyyyyyyyyyyyyyyy
        roles = ", ".join(
            role.mention for role in user.roles if role.name != "@everyone"
        )

        # Infractions
        api_response = await self.bot.http_session.get(
            url=URLs.site_infractions_user.format(user_id=user.id),
            params={"hidden": hidden},
            headers=self.headers
        )

        infractions = await api_response.json()

        infr_total = 0
        infr_active = 0

        # At least it's readable.
        for infr in infractions:
            if infr["active"]:
                infr_active += 1

            infr_total += 1

        # Let's build the embed now
        embed = Embed(
            title=name,
            description=textwrap.dedent(f"""
                **User Information**
                Created: {created}
                Profile: {user.mention}
                ID: {user.id}

                **Member Information**
                Joined: {joined}
                Roles: {roles or None}

                **Infractions**
                Total: {infr_total}
                Active: {infr_active}
            """)
        )

        embed.set_thumbnail(url=user.avatar_url_as(format="png"))
        embed.colour = user.top_role.colour if roles else Colour.blurple()

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Information(bot))
    log.info("Cog loaded: Information")
