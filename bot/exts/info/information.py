import colorsys
import pprint
import textwrap
from collections import defaultdict
from collections.abc import Mapping
from textwrap import shorten
from typing import Any, TYPE_CHECKING

import rapidfuzz
from discord import AllowedMentions, Colour, Embed, Guild, Message, Role
from discord.ext.commands import BucketType, Cog, Context, command, group, has_any_role
from discord.utils import escape_markdown
from pydis_core.site_api import ResponseCodeError
from pydis_core.utils.members import get_or_fetch_member
from pydis_core.utils.paste_service import PasteFile, PasteTooLongError, PasteUploadError, send_to_paste_service

from bot import constants
from bot.bot import Bot
from bot.constants import BaseURLs, Emojis
from bot.converters import MemberOrUser
from bot.decorators import in_whitelist
from bot.errors import NonExistentRoleError
from bot.log import get_logger
from bot.pagination import LinePaginator
from bot.utils import time
from bot.utils.channel import is_mod_channel, is_staff_channel
from bot.utils.checks import cooldown_with_role_bypass, has_no_roles_check, in_whitelist_check
from bot.utils.messages import send_denial

log = get_logger(__name__)

DEFAULT_RULES_DESCRIPTION = (
    "The rules and guidelines that apply to this community can be found on"
    " our [rules page](https://www.pythondiscord.com/pages/rules). We expect"
    " all members of the community to have read and understood these."
)

if TYPE_CHECKING:
    from bot.exts.moderation.defcon import Defcon
    from bot.exts.moderation.watchchannels.bigbrother import BigBrother
    from bot.exts.recruitment.talentpool._cog import TalentPool


class Information(Cog):
    """A cog with commands for generating embeds with server info, such as server stats and user info."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @staticmethod
    def get_channel_type_counts(guild: Guild) -> defaultdict[str, int]:
        """Return the total amounts of the various types of channels in `guild`."""
        channel_counter = defaultdict(int)

        for channel in guild.channels:
            if is_staff_channel(channel):
                channel_counter["staff"] += 1
            else:
                channel_counter[str(channel.type)] += 1

        return channel_counter

    @staticmethod
    def join_role_stats(role_ids: list[int], guild: Guild, name: str | None = None) -> dict[str, int]:
        """Return a dictionary with the number of `members` of each role given, and the `name` for this joined group."""
        member_count = 0
        for role_id in role_ids:
            if (role := guild.get_role(role_id)) is not None:
                member_count += len(role.members)
            else:
                raise NonExistentRoleError(role_id)
        return {name or role.name.title(): member_count}

    @staticmethod
    def get_member_counts(guild: Guild) -> dict[str, int]:
        """Return the total number of members for certain roles in `guild`."""
        role_ids = [constants.Roles.helpers, constants.Roles.mod_team, constants.Roles.admins,
                    constants.Roles.owners, constants.Roles.contributors]

        role_stats = {}
        for role_id in role_ids:
            role_stats.update(Information.join_role_stats([role_id], guild))
        role_stats.update(
            Information.join_role_stats([constants.Roles.project_leads, constants.Roles.domain_leads], guild, "Leads")
        )
        return role_stats

    async def get_extended_server_info(self, ctx: Context) -> str:
        """Return additional server info only visible in moderation channels."""
        talentpool_info = ""
        talentpool_cog: TalentPool | None = self.bot.get_cog("Talentpool")
        if talentpool_cog:
            num_nominated = len(await talentpool_cog.api.get_nominations(active=True))
            talentpool_info = f"Nominated: {num_nominated}\n"

        bb_info = ""
        bb_cog: BigBrother | None = self.bot.get_cog("Big Brother")
        if bb_cog:
            bb_info = f"BB-watched: {len(bb_cog.watched_users)}\n"

        defcon_info = ""
        defcon_cog: Defcon | None = self.bot.get_cog("Defcon")
        if defcon_cog:
            threshold = time.humanize_delta(defcon_cog.threshold) if defcon_cog.threshold else "-"
            defcon_info = f"Defcon threshold: {threshold}\n"

        verification = f"Verification level: {ctx.guild.verification_level.name}\n"

        python_general = self.bot.get_channel(constants.Channels.python_general)

        return textwrap.dedent(f"""
            {talentpool_info}\
            {bb_info}\
            {defcon_info}\
            {verification}\
            {python_general.mention} cooldown: {python_general.slowmode_delay}s
        """)

    @has_any_role(*constants.STAFF_PARTNERS_COMMUNITY_ROLES)
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
            colour=Colour.og_blurple()
        )

        await LinePaginator.paginate(role_list, ctx, embed, empty=False)

    @has_any_role(*constants.STAFF_PARTNERS_COMMUNITY_ROLES)
    @command(name="role")
    async def role_info(self, ctx: Context, *roles: Role | str) -> None:
        """
        Return information on a role or list of roles.

        To specify multiple roles just add to the arguments, delimit roles with spaces in them using quotation marks.
        """
        parsed_roles = set()
        failed_roles = set()

        all_roles = {role.id: role.name for role in ctx.guild.roles}
        for role_name in roles:
            if isinstance(role_name, Role):
                # Role conversion has already succeeded
                parsed_roles.add(role_name)
                continue

            match = rapidfuzz.process.extractOne(
                role_name, all_roles, score_cutoff=80,
                scorer=rapidfuzz.fuzz.ratio
            )

            if not match:
                failed_roles.add(role_name)
                continue

            # `match` is a (role name, score, role id) tuple
            role = ctx.guild.get_role(match[2])
            parsed_roles.add(role)

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
        embed = Embed(colour=Colour.og_blurple(), title="Server Information")

        created = time.format_relative(ctx.guild.created_at)
        num_roles = len(ctx.guild.roles) - 1  # Exclude @everyone

        # Server Features are only useful in certain channels
        if ctx.channel.id in (
            *constants.MODERATION_CHANNELS,
            constants.Channels.dev_core,
        ):
            features = f"\nFeatures: {', '.join(ctx.guild.features)}"
        else:
            features = ""

        # Member status
        py_invite = await self.bot.fetch_invite(constants.Guild.invite)
        online_presences = py_invite.approximate_presence_count
        offline_presences = py_invite.approximate_member_count - online_presences
        member_status = (
            f"{constants.Emojis.status_online} {online_presences:,} "
            f"{constants.Emojis.status_offline} {offline_presences:,}"
        )

        embed.description = (
            f"Created: {created}"
            f"{features}"
            f"\nRoles: {num_roles}"
            f"\nMember status: {member_status}"
        )
        embed.set_thumbnail(url=ctx.guild.icon.url)

        # Members
        total_members = f"{ctx.guild.member_count:,}"
        member_counts = self.get_member_counts(ctx.guild)
        member_info = "\n".join(f"{role}: {count}" for role, count in member_counts.items())
        embed.add_field(name=f"Members: {total_members}", value=member_info)

        # Channels
        total_channels = len(ctx.guild.channels)
        channel_counts = self.get_channel_type_counts(ctx.guild)
        channel_info = "\n".join(
            f"{channel.title()}: {count}" for channel, count in sorted(channel_counts.items())
        )
        embed.add_field(name=f"Channels: {total_channels}", value=channel_info)

        # Additional info if ran in moderation channels
        if is_mod_channel(ctx.channel):
            embed.add_field(name="Moderation:", value=await self.get_extended_server_info(ctx))

        await ctx.send(embed=embed)

    @command(name="user", aliases=["user_info", "member", "member_info", "u"])
    async def user_info(self, ctx: Context, user_or_message: MemberOrUser | Message = None) -> None:
        """Returns info about a user."""
        if passed_as_message := isinstance(user_or_message, Message):
            user = user_or_message.author
        else:
            user = user_or_message

        if user is None:
            user = ctx.author

        # Do a role check if this is being executed on someone other than the caller
        elif user != ctx.author and await has_no_roles_check(ctx, *constants.MODERATION_ROLES):
            await ctx.send("You may not use this command on users other than yourself.")
            return

        # Will redirect to #bot-commands if it fails.
        if in_whitelist_check(ctx, roles=constants.STAFF_PARTNERS_COMMUNITY_ROLES):
            embed = await self.create_user_embed(ctx, user, passed_as_message)
            await ctx.send(embed=embed)

    async def create_user_embed(self, ctx: Context, user: MemberOrUser, passed_as_message: bool) -> Embed:
        """Creates an embed containing information on the `user`."""
        on_server = bool(await get_or_fetch_member(ctx.guild, user.id))

        created = time.format_relative(user.created_at)

        name = str(user)
        if on_server and user.nick:
            name = f"{user.nick} ({name})"
        name = escape_markdown(name)

        if passed_as_message:
            name += " - From Message"

        if user.public_flags.verified_bot:
            name += f" {constants.Emojis.verified_bot}"
        elif user.bot:
            name += f" {constants.Emojis.bot}"

        badges = []

        for badge, is_set in user.public_flags:
            if is_set and (emoji := getattr(constants.Emojis, f"badge_{badge}", None)):
                badges.append(emoji)

        if on_server:
            if user.joined_at:
                joined = time.format_relative(user.joined_at)
            else:
                joined = "Unable to get join date"

            # The 0 is for excluding the default @everyone role,
            # and the -1 is for reversing the order of the roles to highest to lowest in hierarchy.
            roles = ", ".join(role.mention for role in user.roles[:0:-1])
            membership = {"Joined": joined, "Verified": not user.pending, "Roles": roles or None}
            if not is_mod_channel(ctx.channel):
                membership.pop("Verified")

            membership = textwrap.dedent("\n".join([f"{key}: {value}" for key, value in membership.items()]))
        else:
            membership = "The user is not a member of the server"

        fields = [
            (
                "User information",
                textwrap.dedent(f"""
                    Created: {created}
                    Profile: {user.mention}
                    ID: {user.id}
                """).strip()
            ),
            (
                "Member information",
                membership
            ),
            await self.user_messages(user),
        ]

        # Show more verbose output in moderation channels for infractions and nominations
        if is_mod_channel(ctx.channel):
            fields.append(await self.expanded_user_infraction_counts(user))
            fields.append(await self.user_nomination_counts(user))
            fields.append(await self.user_alt_count(user))
        else:
            fields.append(await self.basic_user_infraction_counts(user))

        # Let's build the embed now
        embed = Embed(
            title=name,
            description=" ".join(badges)
        )

        for field_name, field_content in fields:
            embed.add_field(name=field_name, value=field_content, inline=False)

        embed.set_thumbnail(url=user.display_avatar.url)
        embed.colour = user.colour if user.colour != Colour.default() else Colour.og_blurple()

        return embed

    async def user_alt_count(self, user: MemberOrUser) -> tuple[str, int | str]:
        """Get the number of alts for the given member."""
        try:
            resp = await self.bot.api_client.get(f"bot/users/{user.id}")
            return ("Associated accounts", len(resp["alts"]) or "No associated accounts")
        except ResponseCodeError as e:
            # If user is not found, return a soft-error regarding this.
            if e.response.status == 404:
                return ("Associated accounts", "User not found in site database.")

            # If we have any other issue, re-raise the exception
            raise e


    async def basic_user_infraction_counts(self, user: MemberOrUser) -> tuple[str, str]:
        """Gets the total and active infraction counts for the given `member`."""
        infractions = await self.bot.api_client.get(
            "bot/infractions",
            params={
                "hidden": "False",
                "user__id": str(user.id)
            }
        )

        total_infractions = len(infractions)
        active_infractions = sum(infraction["active"] for infraction in infractions)

        infraction_output = f"Total: {total_infractions}\nActive: {active_infractions}"

        return "Infractions", infraction_output

    async def expanded_user_infraction_counts(self, user: MemberOrUser) -> tuple[str, str]:
        """
        Gets expanded infraction counts for the given `member`.

        The counts will be split by infraction type and the number of active infractions for each type will indicated
        in the output as well.
        """
        infractions = await self.bot.api_client.get(
            "bot/infractions",
            params={
                "user__id": str(user.id)
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
                infraction_active = "active" if infraction["active"] else "inactive"

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

    async def user_nomination_counts(self, user: MemberOrUser) -> tuple[str, str]:
        """Gets the active and historical nomination counts for the given `member`."""
        nominations = await self.bot.api_client.get(
            "bot/nominations",
            params={
                "user__id": str(user.id)
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

    async def user_messages(self, user: MemberOrUser) -> tuple[str, str]:
        """
        Gets the amount of messages for `member`.

        Fetches information from the metricity database that's hosted by the site.
        If the database returns a code besides a 404, then many parts of the bot are broken including this one.
        """
        activity_output = []

        try:
            user_activity = await self.bot.api_client.get(f"bot/users/{user.id}/metricity_data")
        except ResponseCodeError as e:
            if e.status == 404:
                activity_output = "No activity"
        else:
            total_message_text = (
                f"{user_activity['total_messages']:,}" if user_activity["total_messages"] else "No messages"
            )
            activity_blocks_text = (
                f"{user_activity['activity_blocks']:,}" if user_activity["activity_blocks"] else "No activity"
            )
            activity_output.append(total_message_text)
            activity_output.append(activity_blocks_text)

            activity_output = "\n".join(
                f"{name}: {metric}"
                for name, metric in zip(["Messages", "Activity blocks"], activity_output, strict=True)
            )

        return "Activity", activity_output

    def format_fields(self, mapping: Mapping[str, Any], field_width: int | None = None) -> str:
        """Format a mapping to be readable to a human."""
        # sorting is technically superfluous but nice if you want to look for a specific field
        fields = sorted(mapping.items(), key=lambda item: item[0])

        if field_width is None:
            field_width = len(max(mapping.keys(), key=len))

        out = ""

        for key, val in fields:
            if isinstance(val, dict):
                # if we have dicts inside dicts we want to apply the same treatment to the inner dictionaries
                inner_width = int(field_width * 1.6)
                val = "\n" + self.format_fields(val, field_width=inner_width)

            elif isinstance(val, str):
                # split up text since it might be long
                text = textwrap.fill(val, width=100, replace_whitespace=False)

                # indent it, I guess you could do this with `wrap` and `join` but this is nicer
                val = textwrap.indent(text, " " * (field_width + len(": ")))

                # the first line is already indented so we `str.lstrip` it
                val = val.lstrip()

            if key == "color":
                # makes the base 10 representation of a hex number readable to humans
                val = hex(val)

            out += "{0:>{width}}: {1}\n".format(key, val, width=field_width)

        # remove trailing whitespace
        return out.rstrip()

    async def send_raw_content(self, ctx: Context, message: Message, json: bool = False) -> None:
        """
        Send information about the raw API response for a `discord.Message`.

        If `json` is True, send the information in a copy-pasteable Python format.
        """
        if not message.channel.permissions_for(ctx.author).read_messages:
            await ctx.send(":x: You do not have permissions to see the channel this message is in.")
            return

        # I *guess* it could be deleted right as the command is invoked but I felt like it wasn't worth handling
        # doing this extra request is also much easier than trying to convert everything back into a dictionary again
        raw_data = await ctx.bot.http.get_message(message.channel.id, message.id)

        lines = []

        def add_content(title: str, content: str) -> None:
            lines.append(f"== {title} ==\n")
            # Replace backticks as it breaks out of code blocks.
            # An invisible character seemed to be the most reasonable solution.
            lines.append(content.replace("`", "`\u200b"))

        if message.content:
            add_content("Raw message", message.content)

        transformer = pprint.pformat if json else self.format_fields
        for field_name in ("embeds", "attachments"):
            data = raw_data[field_name]

            if not data:
                continue

            total = len(data)
            for current, item in enumerate(data, start=1):
                title = f"Raw {field_name} ({current}/{total})"
                add_content(title, transformer(item))

        output = "\n".join(lines)
        if len(output) < 2000-8:  # To cover the backticks and newlines added below.
            await ctx.send(f"```\n{output}\n```", allowed_mentions=AllowedMentions.none())
            return

        file = PasteFile(content=output, lexer="text")
        try:
            resp = await send_to_paste_service(
                files=[file],
                http_session=self.bot.http_session,
                paste_url=BaseURLs.paste_url,
            )
            message = f"Message was too long for Discord, posted the output to [our pastebin]({resp.link})."
        except PasteTooLongError:
            message = f"{Emojis.cross_mark} Too long to upload to paste service."
        except PasteUploadError:
            message = f"{Emojis.cross_mark} Failed to upload to paste service."

        await ctx.send(message)

    @cooldown_with_role_bypass(2, 60 * 3, BucketType.member, bypass_roles=constants.STAFF_PARTNERS_COMMUNITY_ROLES)
    @group(invoke_without_command=True)
    @in_whitelist(channels=(constants.Channels.bot_commands,), roles=constants.STAFF_PARTNERS_COMMUNITY_ROLES)
    async def raw(self, ctx: Context, message: Message | None = None) -> None:
        """Shows information about the raw API response."""
        if message is None:
            if (reference := ctx.message.reference) and isinstance(reference.resolved, Message):
                message = reference.resolved
            else:
                await send_denial(
                    ctx, "Missing message argument. Please provide a message ID/link or reply to a message."
                )
                return

        await self.send_raw_content(ctx, message)

    @raw.command()
    async def json(self, ctx: Context, message: Message | None = None) -> None:
        """Shows information about the raw API response in a copy-pasteable Python format."""
        if message is None:
            if (reference := ctx.message.reference) and isinstance(reference.resolved, Message):
                message = reference.resolved
            else:
                await send_denial(
                    ctx, "Missing message argument. Please provide a message ID/link or reply to a message."
                )
                return

        await self.send_raw_content(ctx, message, json=True)

    async def _set_rules_command_help(self) -> None:
        help_string = f"{self.rules.help}\n\n"
        help_string += "__Available keywords per rule__:\n\n"

        full_rules = await self.bot.api_client.get("rules", params={"link_format": "md"})

        for index, (_, keywords) in enumerate(full_rules, start=1):
            help_string += f"**Rule {index}**: {', '.join(keywords)}\n\r"

        self.rules.help = help_string

    @command(aliases=("rule",))
    async def rules(self, ctx: Context, *, args: str | None) -> set[int] | None:
        """
        Provides a link to all rules or, if specified, displays specific rule(s).

        It accepts either rule numbers or particular keywords that map to a particular rule.
        Rule numbers and keywords can be sent in any order.
        """
        rules_embed = Embed(title="Rules", color=Colour.og_blurple(), url="https://www.pythondiscord.com/pages/rules")
        keywords, rule_numbers = [], []

        full_rules = await self.bot.api_client.get("rules", params={"link_format": "md"})
        keyword_to_rule_number = dict()

        for rule_number, (_, rule_keywords) in enumerate(full_rules, start=1):
            for rule_keyword in rule_keywords:
                keyword_to_rule_number[rule_keyword] = rule_number

        if args:
            for word in args.split(maxsplit=100):
                try:
                    rule_numbers.append(int(word))
                except ValueError:
                    # Stop on first invalid keyword/index to allow for normal messaging after
                    if (kw := word.lower()) not in keyword_to_rule_number:
                        break
                    keywords.append(kw)

        if not rule_numbers and not keywords:
            # Neither rules nor keywords were submitted. Return the default description.
            rules_embed.description = DEFAULT_RULES_DESCRIPTION
            await ctx.send(embed=rules_embed)
            return None

        # Remove duplicates and sort the rule indices
        rule_numbers = sorted(set(rule_numbers))

        invalid = ", ".join(
            str(rule_number) for rule_number in rule_numbers
            if rule_number < 1 or rule_number > len(full_rules))

        if invalid:
            await ctx.send(shorten(":x: Invalid rule indices: " + invalid, 75, placeholder=" ..."))
            return None

        final_rules = []
        final_rule_numbers = {keyword_to_rule_number[keyword] for keyword in keywords}
        final_rule_numbers.update(rule_numbers)

        for rule_number in sorted(final_rule_numbers):
            self.bot.stats.incr(f"rule_uses.{rule_number}")
            final_rules.append(f"**{rule_number}.** {full_rules[rule_number - 1][0]}")

        await LinePaginator.paginate(final_rules, ctx, rules_embed, max_lines=3)

        return final_rule_numbers

    async def cog_load(self) -> None:
        """Carry out cog asynchronous initialisation."""
        await self._set_rules_command_help()


async def setup(bot: Bot) -> None:
    """Load the Information cog."""
    await bot.add_cog(Information(bot))
