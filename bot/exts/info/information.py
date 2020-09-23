import colorsys
import logging
import pprint
import textwrap
from collections import Counter, defaultdict
from typing import Any, DefaultDict, Dict, Mapping, Optional, Tuple, Union

from discord import ChannelType, Colour, CustomActivity, Embed, Guild, Member, Message, Role, Status, utils
from discord.abc import GuildChannel
from discord.ext.commands import BucketType, Cog, Context, Paginator, command, group
from discord.utils import escape_markdown

from bot import constants
from bot.bot import Bot
from bot.decorators import in_whitelist, with_role
from bot.pagination import LinePaginator
from bot.utils.checks import InWhitelistCheckFailure, cooldown_with_role_bypass, with_role_check
from bot.utils.time import time_since

log = logging.getLogger(__name__)

STATUS_EMOTES = {
    Status.online: constants.Emojis.status_online,
    Status.idle: constants.Emojis.status_idle,
    Status.dnd: constants.Emojis.status_dnd,
    Status.offline: constants.Emojis.status_offline,
}


class Information(Cog):
    """A cog with commands for generating embeds with server info, such as server stats and user info."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @staticmethod
    def is_staff_channel(guild: Guild, channel: GuildChannel) -> bool:
        """Determines if a given channel is staff-only."""
        if channel.type is ChannelType.category:
            return False

        # Channel is staff-only if staff have explicit read allow perms
        # and @everyone has explicit read deny perms
        return any(
            channel.overwrites_for(guild.get_role(staff_role)).read_messages is True
            and channel.overwrites_for(guild.default_role).read_messages is False
            for staff_role in constants.STAFF_ROLES
        )

    @staticmethod
    def get_channel_type_counts(guild: Guild) -> DefaultDict[str, int]:
        """Return the total amounts of the various types of channels in `guild`."""
        channel_counter = defaultdict(int)

        for channel in guild.channels:
            if Information.is_staff_channel(guild, channel):
                channel_counter["staff"] += 1
            else:
                channel_counter[str(channel.type)] += 1

        return channel_counter

    @staticmethod
    def get_member_counts(guild: Guild) -> Dict[str, int]:
        """Return the total number of members for certain roles in `guild`."""
        roles = (
            guild.get_role(role_id) for role_id in (
                constants.Roles.helpers, constants.Roles.moderators, constants.Roles.admins,
                constants.Roles.owners, constants.Roles.contributors,
            )
        )
        return {role.name: len(role.members) for role in roles}

    def get_extended_server_info(self, guild: Guild) -> str:
        """Return additional server info only visible in moderation channels."""
        unverified_count = guild.member_count - len(guild.get_role(constants.Roles.verified).members)
        talentpool_count = len(self.bot.get_cog("Talentpool").watched_users)
        bb_count = len(self.bot.get_cog("Big Brother").watched_users)

        defcon_cog = self.bot.get_cog("Defcon")
        defcon_status = "Enabled" if defcon_cog.enabled else "Disabled"
        defcon_days = defcon_cog.days.days if defcon_cog.enabled else "-"
        python_general = self.bot.get_channel(constants.Channels.python_discussion)

        return textwrap.dedent(f"""
            Unverified: {unverified_count:,}
            Nominated: {talentpool_count}
            BB-watched: {bb_count}

            Defcon status: {defcon_status}
            Defcon days: {defcon_days}
            {python_general.mention} cooldown: {python_general.slowmode_delay}s
        """)

    @with_role(*constants.MODERATION_ROLES)
    @command(name="roles")
    async def roles_info(self, ctx: Context) -> None:
        """Returns a list of all roles and their corresponding IDs."""
        # Sort the roles alphabetically and remove the @everyone role
        roles = sorted(ctx.guild.roles[1:], key=lambda role: role.name)

        # Build a list
        role_list = []
        for role in roles:
            role_list.append(f"`{role.id}` - {role.mention}")

        # Build an embed
        embed = Embed(
            title=f"Role information (Total {len(roles)} role{'s' * (len(role_list) > 1)})",
            colour=Colour.blurple()
        )

        await LinePaginator.paginate(role_list, ctx, embed, empty=False)

    @with_role(*constants.MODERATION_ROLES)
    @command(name="role")
    async def role_info(self, ctx: Context, *roles: Union[Role, str]) -> None:
        """
        Return information on a role or list of roles.

        To specify multiple roles just add to the arguments, delimit roles with spaces in them using quotation marks.
        """
        parsed_roles = []
        failed_roles = []

        for role_name in roles:
            if isinstance(role_name, Role):
                # Role conversion has already succeeded
                parsed_roles.append(role_name)
                continue

            role = utils.find(lambda r: r.name.lower() == role_name.lower(), ctx.guild.roles)

            if not role:
                failed_roles.append(role_name)
                continue

            parsed_roles.append(role)

        if failed_roles:
            await ctx.send(f":x: Could not retrieve the following roles: {', '.join(failed_roles)}")

        for role in parsed_roles:
            h, s, v = colorsys.rgb_to_hsv(*role.colour.to_rgb())

            embed = Embed(
                title=f"{role.name} info",
                colour=role.colour,
            )
            embed.add_field(name="ID", value=role.id, inline=True)
            embed.add_field(name="Colour (RGB)", value=f"#{role.colour.value:0>6x}", inline=True)
            embed.add_field(name="Colour (HSV)", value=f"{h:.2f} {s:.2f} {v}", inline=True)
            embed.add_field(name="Member count", value=len(role.members), inline=True)
            embed.add_field(name="Position", value=role.position)
            embed.add_field(name="Permission code", value=role.permissions.value, inline=True)

            await ctx.send(embed=embed)

    @command(name="server", aliases=["server_info", "guild", "guild_info"])
    async def server_info(self, ctx: Context) -> None:
        """Returns an embed full of server information."""
        embed = Embed(
            colour=Colour.blurple(),
            title="Server Information",
        )

        created = time_since(ctx.guild.created_at, precision="days")
        region = ctx.guild.region
        num_roles = len(ctx.guild.roles) - 1  # Exclude @everyone

        # Server Features are only useful in certain channels
        if ctx.channel.id in (
            *constants.MODERATION_CHANNELS, constants.Channels.dev_core, constants.Channels.dev_contrib
        ):
            features = f"\nFeatures: {', '.join(ctx.guild.features)}"
        else:
            features = ""

        embed.description = textwrap.dedent(f"""
            Created: {created}
            Voice region: {region}{features}
            Roles: {num_roles}
        """)
        embed.set_thumbnail(url=ctx.guild.icon_url)

        # Members
        total_members = ctx.guild.member_count
        member_counts = self.get_member_counts(ctx.guild)
        member_info = "\n".join(
            f"{role.title()}: {count}" for role, count in member_counts.items()
        )
        embed.add_field(name=f"Members: {total_members}", value=member_info)

        # Channels
        total_channels = len(ctx.guild.channels)
        channel_counts = self.get_channel_type_counts(ctx.guild)
        channel_info = "\n".join(
            f"{channel.title()}: {count}" for channel, count in sorted(channel_counts.items())
        )
        embed.add_field(name=f"Channels: {total_channels}", value=channel_info)

        # Member status
        status_count = Counter(member.status for member in ctx.guild.members)
        member_status = " ".join(
            f"{emoji} {status_count[status]:,}" for status, emoji in STATUS_EMOTES.items()
        )
        embed.add_field(name="Member Status:", value=member_status, inline=False)

        # Additional info if ran in moderation channels
        if ctx.channel.id in constants.MODERATION_CHANNELS:
            embed.add_field(
                name="Moderation Information:", value=self.get_extended_server_info(ctx.guild)
            )

        await ctx.send(embed=embed)

    @command(name="user", aliases=["user_info", "member", "member_info"])
    async def user_info(self, ctx: Context, user: Member = None) -> None:
        """Returns info about a user."""
        if user is None:
            user = ctx.author

        # Do a role check if this is being executed on someone other than the caller
        elif user != ctx.author and not with_role_check(ctx, *constants.MODERATION_ROLES):
            await ctx.send("You may not use this command on users other than yourself.")
            return

        # Non-staff may only do this in #bot-commands
        if not with_role_check(ctx, *constants.STAFF_ROLES):
            if not ctx.channel.id == constants.Channels.bot_commands:
                raise InWhitelistCheckFailure(constants.Channels.bot_commands)

        embed = await self.create_user_embed(ctx, user)

        await ctx.send(embed=embed)

    async def create_user_embed(self, ctx: Context, user: Member) -> Embed:
        """Creates an embed containing information on the `user`."""
        created = time_since(user.created_at, max_units=3)

        # Custom status
        custom_status = ''
        for activity in user.activities:
            if isinstance(activity, CustomActivity):
                state = ""

                if activity.name:
                    state = escape_markdown(activity.name)

                emoji = ""
                if activity.emoji:
                    # If an emoji is unicode use the emoji, else write the emote like :abc:
                    if not activity.emoji.id:
                        emoji += activity.emoji.name + " "
                    else:
                        emoji += f"`:{activity.emoji.name}:` "

                custom_status = f'Status: {emoji}{state}\n'

        name = str(user)
        if user.nick:
            name = f"{user.nick} ({name})"

        badges = []

        for badge, is_set in user.public_flags:
            if is_set and (emoji := getattr(constants.Emojis, f"badge_{badge}", None)):
                badges.append(emoji)

        joined = time_since(user.joined_at, max_units=3)
        roles = ", ".join(role.mention for role in user.roles[1:])

        desktop_status = STATUS_EMOTES.get(user.desktop_status, constants.Emojis.status_online)
        web_status = STATUS_EMOTES.get(user.web_status, constants.Emojis.status_online)
        mobile_status = STATUS_EMOTES.get(user.mobile_status, constants.Emojis.status_online)

        fields = [
            (
                "User information",
                textwrap.dedent(f"""
                    Created: {created}
                    Profile: {user.mention}
                    ID: {user.id}
                    {custom_status}
                """).strip()
            ),
            (
                "Member information",
                textwrap.dedent(f"""
                    Joined: {joined}
                    Roles: {roles or None}
                """).strip()
            ),
            (
                "Status",
                textwrap.dedent(f"""
                    {desktop_status} Desktop
                    {web_status} Web
                    {mobile_status} Mobile
                """).strip()
            )
        ]

        # Show more verbose output in moderation channels for infractions and nominations
        if ctx.channel.id in constants.MODERATION_CHANNELS:
            fields.append(await self.expanded_user_infraction_counts(user))
            fields.append(await self.user_nomination_counts(user))
        else:
            fields.append(await self.basic_user_infraction_counts(user))

        # Let's build the embed now
        embed = Embed(
            title=name,
            description=" ".join(badges)
        )

        for field_name, field_content in fields:
            embed.add_field(name=field_name, value=field_content, inline=False)

        embed.set_thumbnail(url=user.avatar_url_as(static_format="png"))
        embed.colour = user.top_role.colour if roles else Colour.blurple()

        return embed

    async def basic_user_infraction_counts(self, member: Member) -> Tuple[str, str]:
        """Gets the total and active infraction counts for the given `member`."""
        infractions = await self.bot.api_client.get(
            'bot/infractions',
            params={
                'hidden': 'False',
                'user__id': str(member.id)
            }
        )

        total_infractions = len(infractions)
        active_infractions = sum(infraction['active'] for infraction in infractions)

        infraction_output = f"Total: {total_infractions}\nActive: {active_infractions}"

        return "Infractions", infraction_output

    async def expanded_user_infraction_counts(self, member: Member) -> Tuple[str, str]:
        """
        Gets expanded infraction counts for the given `member`.

        The counts will be split by infraction type and the number of active infractions for each type will indicated
        in the output as well.
        """
        infractions = await self.bot.api_client.get(
            'bot/infractions',
            params={
                'user__id': str(member.id)
            }
        )

        infraction_output = []
        if not infractions:
            infraction_output.append("No infractions")
        else:
            # Count infractions split by `type` and `active` status for this user
            infraction_types = set()
            infraction_counter = defaultdict(int)
            for infraction in infractions:
                infraction_type = infraction["type"]
                infraction_active = 'active' if infraction["active"] else 'inactive'

                infraction_types.add(infraction_type)
                infraction_counter[f"{infraction_active} {infraction_type}"] += 1

            # Format the output of the infraction counts
            for infraction_type in sorted(infraction_types):
                active_count = infraction_counter[f"active {infraction_type}"]
                total_count = active_count + infraction_counter[f"inactive {infraction_type}"]

                line = f"{infraction_type.capitalize()}s: {total_count}"
                if active_count:
                    line += f" ({active_count} active)"

                infraction_output.append(line)

        return "Infractions", "\n".join(infraction_output)

    async def user_nomination_counts(self, member: Member) -> Tuple[str, str]:
        """Gets the active and historical nomination counts for the given `member`."""
        nominations = await self.bot.api_client.get(
            'bot/nominations',
            params={
                'user__id': str(member.id)
            }
        )

        output = []

        if not nominations:
            output.append("No nominations")
        else:
            count = len(nominations)
            is_currently_nominated = any(nomination["active"] for nomination in nominations)
            nomination_noun = "nomination" if count == 1 else "nominations"

            if is_currently_nominated:
                output.append(f"This user is **currently** nominated\n({count} {nomination_noun} in total)")
            else:
                output.append(f"This user has {count} historical {nomination_noun}, but is currently not nominated.")

        return "Nominations", "\n".join(output)

    def format_fields(self, mapping: Mapping[str, Any], field_width: Optional[int] = None) -> str:
        """Format a mapping to be readable to a human."""
        # sorting is technically superfluous but nice if you want to look for a specific field
        fields = sorted(mapping.items(), key=lambda item: item[0])

        if field_width is None:
            field_width = len(max(mapping.keys(), key=len))

        out = ''

        for key, val in fields:
            if isinstance(val, dict):
                # if we have dicts inside dicts we want to apply the same treatment to the inner dictionaries
                inner_width = int(field_width * 1.6)
                val = '\n' + self.format_fields(val, field_width=inner_width)

            elif isinstance(val, str):
                # split up text since it might be long
                text = textwrap.fill(val, width=100, replace_whitespace=False)

                # indent it, I guess you could do this with `wrap` and `join` but this is nicer
                val = textwrap.indent(text, ' ' * (field_width + len(': ')))

                # the first line is already indented so we `str.lstrip` it
                val = val.lstrip()

            if key == 'color':
                # makes the base 10 representation of a hex number readable to humans
                val = hex(val)

            out += '{0:>{width}}: {1}\n'.format(key, val, width=field_width)

        # remove trailing whitespace
        return out.rstrip()

    @cooldown_with_role_bypass(2, 60 * 3, BucketType.member, bypass_roles=constants.STAFF_ROLES)
    @group(invoke_without_command=True, enabled=False)
    @in_whitelist(channels=(constants.Channels.bot_commands,), roles=constants.STAFF_ROLES)
    async def raw(self, ctx: Context, *, message: Message, json: bool = False) -> None:
        """Shows information about the raw API response."""
        # I *guess* it could be deleted right as the command is invoked but I felt like it wasn't worth handling
        # doing this extra request is also much easier than trying to convert everything back into a dictionary again
        raw_data = await ctx.bot.http.get_message(message.channel.id, message.id)

        paginator = Paginator()

        def add_content(title: str, content: str) -> None:
            paginator.add_line(f'== {title} ==\n')
            # replace backticks as it breaks out of code blocks. Spaces seemed to be the most reasonable solution.
            # we hope it's not close to 2000
            paginator.add_line(content.replace('```', '`` `'))
            paginator.close_page()

        if message.content:
            add_content('Raw message', message.content)

        transformer = pprint.pformat if json else self.format_fields
        for field_name in ('embeds', 'attachments'):
            data = raw_data[field_name]

            if not data:
                continue

            total = len(data)
            for current, item in enumerate(data, start=1):
                title = f'Raw {field_name} ({current}/{total})'
                add_content(title, transformer(item))

        for page in paginator.pages:
            await ctx.send(page)

    @raw.command(enabled=False)
    async def json(self, ctx: Context, message: Message) -> None:
        """Shows information about the raw API response in a copy-pasteable Python format."""
        await ctx.invoke(self.raw, message=message, json=True)


def setup(bot: Bot) -> None:
    """Load the Information cog."""
    bot.add_cog(Information(bot))
