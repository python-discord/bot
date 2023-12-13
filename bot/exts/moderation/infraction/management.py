import gettext
import re
import textwrap
import typing as t

import discord
from discord.ext import commands
from discord.ext.commands import Context
from discord.utils import escape_markdown
from pydis_core.utils.members import get_or_fetch_member

from bot import constants
from bot.bot import Bot
from bot.constants import Categories
from bot.converters import DurationOrExpiry, Infraction, MemberOrUser, Snowflake, UnambiguousUser
from bot.decorators import ensure_future_timestamp
from bot.errors import InvalidInfractionError
from bot.exts.moderation.infraction import _utils
from bot.exts.moderation.infraction.infractions import Infractions
from bot.log import get_logger
from bot.pagination import LinePaginator
from bot.utils import messages, time
from bot.utils.channel import is_in_category, is_mod_channel
from bot.utils.modlog import send_log_message
from bot.utils.time import unpack_duration

log = get_logger(__name__)

NO_DURATION_INFRACTIONS = ("note", "warning", "kick")

FAILED_DM_SYMBOL = constants.Emojis.failmail
HIDDEN_INFRACTION_SYMBOL = "🕵️"
EDITED_DURATION_SYMBOL = "✏️"

SYMBOLS_GUIDE = f"""
Symbols guide:
\u2003{FAILED_DM_SYMBOL} - The infraction DM failed to deliver.
\u2003{HIDDEN_INFRACTION_SYMBOL} - The infraction is hidden.
\u2003{EDITED_DURATION_SYMBOL}- The duration was edited.
"""


class ModManagement(commands.Cog):
    """Management of infractions."""

    category = "Moderation"

    def __init__(self, bot: Bot):
        self.bot = bot

        # Add the symbols guide to the help embeds of the appropriate commands.
        for command in (
            self.infraction_group,
            self.infraction_search_group,
            self.search_reason,
            self.search_user,
            self.search_by_actor
        ):
            command.help += f"\n{SYMBOLS_GUIDE}"

    @property
    def infractions_cog(self) -> Infractions:
        """Get currently loaded Infractions cog instance."""
        return self.bot.get_cog("Infractions")

    @commands.group(name="infraction", aliases=("infr", "infractions", "inf", "i"), invoke_without_command=True)
    async def infraction_group(self, ctx: Context, infraction: Infraction = None) -> None:
        """
        Infraction management commands.

        If `infraction` is passed then this command fetches that infraction. The `Infraction` converter
        supports 'l', 'last' and 'recent' to get the most recent infraction made by `ctx.author`.
        """
        if infraction is None:
            await ctx.send_help(ctx.command)
            return

        embed = discord.Embed(
            title=f"{self.format_infraction_title(infraction)}",
            colour=discord.Colour.orange()
        )
        await self.send_infraction_list(ctx, embed, [infraction], ignore_fields=("id",))

    @infraction_group.command(name="resend", aliases=("send", "rs", "dm"))
    async def infraction_resend(self, ctx: Context, infraction: Infraction) -> None:
        """Resend a DM to a user about a given infraction of theirs."""
        if infraction["hidden"]:
            await ctx.send(f"{constants.Emojis.failmail} You may not resend hidden infractions.")
            return

        member_id = infraction["user"]["id"]
        member = await get_or_fetch_member(ctx.guild, member_id)
        if not member:
            await ctx.send(f"{constants.Emojis.failmail} Cannot find member `{member_id}` in the guild.")
            return

        id_ = infraction["id"]
        reason = infraction["reason"] or "No reason provided."
        reason += "\n\n**This is a re-sent message for a previously applied infraction which may have been edited.**"

        if await _utils.notify_infraction(infraction, member, reason):
            await ctx.send(f":incoming_envelope: Resent DM for infraction `{id_}`.")
        else:
            await ctx.send(f"{constants.Emojis.failmail} Failed to resend DM for infraction `{id_}`.")

    # region: Edit infraction commands

    @infraction_group.command(name="append", aliases=("amend", "add", "a"))
    async def infraction_append(
        self,
        ctx: Context,
        infraction: Infraction,
        duration: DurationOrExpiry | t.Literal["p", "permanent"] | None,
        *,
        reason: str = None  # noqa: RUF013
    ) -> None:
        """
        Append text and/or edit the duration of an infraction.

        Durations are relative to the time of updating and should be appended with a unit of time.
        Units (∗case-sensitive):
        \u2003`y` - years
        \u2003`m` - months∗
        \u2003`w` - weeks
        \u2003`d` - days
        \u2003`h` - hours
        \u2003`M` - minutes∗
        \u2003`s` - seconds

        Use "l", "last", or "recent" as the infraction ID to specify that the most recent infraction
        authored by the command invoker should be edited.

        Use "p" or "permanent" to mark the infraction as permanent. Alternatively, an ISO 8601
        timestamp can be provided for the duration.

        If a previous infraction reason does not end with an ending punctuation mark, this automatically
        adds a period before the amended reason.
        """  # noqa: RUF002
        old_reason = infraction["reason"]

        if old_reason is not None and reason is not None:
            add_period = not old_reason.endswith((".", "!", "?"))
            reason = old_reason + (". " if add_period else " ") + reason

        await self.infraction_edit(ctx, infraction, duration, reason=reason)

    @infraction_group.command(name="edit", aliases=("e",))
    @ensure_future_timestamp(timestamp_arg=3)
    async def infraction_edit(
        self,
        ctx: Context,
        infraction: Infraction,
        duration: DurationOrExpiry | t.Literal["p", "permanent"] | None,
        *,
        reason: str = None  # noqa: RUF013
    ) -> None:
        """
        Edit the duration and/or the reason of an infraction.

        Durations are relative to the time of updating and should be appended with a unit of time.
        Units (∗case-sensitive):
        \u2003`y` - years
        \u2003`m` - months∗
        \u2003`w` - weeks
        \u2003`d` - days
        \u2003`h` - hours
        \u2003`M` - minutes∗
        \u2003`s` - seconds

        Use "l", "last", or "recent" as the infraction ID to specify that the most recent infraction
        authored by the command invoker should be edited.

        Use "p" or "permanent" to mark the infraction as permanent. Alternatively, an ISO 8601
        timestamp can be provided for the duration.
        """  # noqa: RUF002
        if duration is None and reason is None:
            # Unlike UserInputError, the error handler will show a specified message for BadArgument
            raise commands.BadArgument("Neither a new expiry nor a new reason was specified.")

        infraction_id = infraction["id"]

        request_data = {}
        confirm_messages = []
        log_text = ""

        if duration is not None and not infraction["active"]:
            if (infr_type := infraction["type"]) in ("note", "warning"):
                await ctx.send(f":x: Cannot edit the expiration of a {infr_type}.")
            else:
                await ctx.send(":x: Cannot edit the expiration of an expired infraction.")
            return

        if isinstance(duration, str):
            request_data["expires_at"] = None
            confirm_messages.append("marked as permanent")
        elif duration is not None:
            origin, expiry = unpack_duration(duration)
            # Update `last_applied` if expiry changes.
            request_data["last_applied"] = origin.isoformat()
            request_data["expires_at"] = expiry.isoformat()
            formatted_expiry = time.format_with_duration(expiry, origin)
            confirm_messages.append(f"set to expire on {formatted_expiry}")
        else:
            confirm_messages.append("expiry unchanged")

        if reason:
            request_data["reason"] = reason
            confirm_messages.append("set a new reason")
            log_text += f"""
                Previous reason: {infraction['reason']}
                New reason: {reason}
            """.rstrip()
        else:
            confirm_messages.append("reason unchanged")

        # Update the infraction
        new_infraction = await self.bot.api_client.patch(
            f"bot/infractions/{infraction_id}",
            json=request_data,
        )

        # Get information about the infraction's user
        user_id = new_infraction["user"]
        user = await get_or_fetch_member(ctx.guild, user_id)

        # Re-schedule infraction if the expiration has been updated
        if "expires_at" in request_data:
            # A scheduled task should only exist if the old infraction wasn't permanent
            if infraction["expires_at"]:
                self.infractions_cog.scheduler.cancel(infraction_id)

            # If the infraction was not marked as permanent, schedule a new expiration task
            if request_data["expires_at"]:
                self.infractions_cog.schedule_expiration(new_infraction)
                # Timeouts are handled by Discord itself, so we need to edit the expiry in Discord as well
                if user and infraction["type"] == "timeout":
                    capped, duration = _utils.cap_timeout_duration(expiry)
                    if capped:
                        await _utils.notify_timeout_cap(self.bot, ctx, user)
                    await user.edit(reason=reason, timed_out_until=expiry)

            log_text += f"""
                Previous expiry: {time.until_expiration(infraction['expires_at'])}
                New expiry: {time.until_expiration(new_infraction['expires_at'])}
            """.rstrip()

        changes = " & ".join(confirm_messages)
        await ctx.send(f":ok_hand: Updated infraction #{infraction_id}: {changes}")

        if user:
            user_text = messages.format_user(user)
            thumbnail = user.display_avatar.url
        else:
            user_text = f"<@{user_id}>"
            thumbnail = None

        if any(
                is_in_category(ctx.channel, category)
                for category in (Categories.modmail, Categories.appeals, Categories.appeals_2)
        ):
            jump_url = "(Infraction edited in a ModMail channel.)"
        else:
            jump_url = f"[Click here.]({ctx.message.jump_url})"

        await send_log_message(
            self.bot,
            icon_url=constants.Icons.pencil,
            colour=discord.Colour.og_blurple(),
            title="Infraction edited",
            thumbnail=thumbnail,
            text=textwrap.dedent(f"""
                Member: {user_text}
                Actor: <@{new_infraction['actor']}>
                Edited by: {ctx.message.author.mention}{log_text}
                Jump URL: {jump_url}
            """),
            footer=f"ID: {infraction_id}"
        )

    # endregion
    # region: Search infractions

    @infraction_group.group(name="search", aliases=("s",), invoke_without_command=True)
    async def infraction_search_group(self, ctx: Context, query: UnambiguousUser | Snowflake | str) -> None:
        """Searches for infractions in the database."""
        if isinstance(query, int):
            await self.search_user(ctx, discord.Object(query))
        elif isinstance(query, str):
            await self.search_reason(ctx, query)
        else:
            await self.search_user(ctx, query)

    @infraction_search_group.command(name="user", aliases=("member", "userid"))
    async def search_user(self, ctx: Context, user: MemberOrUser | discord.Object) -> None:
        """Search for infractions by member."""
        infraction_list = await self.bot.api_client.get(
            "bot/infractions/expanded",
            params={"user__id": str(user.id)}
        )

        if isinstance(user, discord.Member | discord.User):
            user_str = escape_markdown(str(user))
        else:
            if infraction_list:
                user_data = infraction_list[0]["user"]
                user_str = escape_markdown(user_data["name"]) + f"#{user_data['discriminator']:04}"
            else:
                user_str = str(user.id)

        formatted_infraction_count = self.format_infraction_count(len(infraction_list))
        embed = discord.Embed(
            title=f"Infractions for {user_str} ({formatted_infraction_count} total)",
            colour=discord.Colour.orange()
        )
        # Manually form mention from ID as discord.Object doesn't have a `.mention` attr
        prefix = f"<@{user.id}> - {user.id}"
        # If the user has alts show in the prefix
        if infraction_list and (alts := infraction_list[0]["user"]["alts"]):
            prefix += f" ({len(alts)} associated {gettext.ngettext('account', 'accounts', len(alts))})"

        await self.send_infraction_list(ctx, embed, infraction_list, prefix, ("user",))

    @infraction_search_group.command(name="reason", aliases=("match", "regex", "re"))
    async def search_reason(self, ctx: Context, reason: str) -> None:
        """Search for infractions by their reason. Use Re2 for matching."""
        try:
            re.compile(reason)
        except re.error as e:
            raise commands.BadArgument(f"Invalid regular expression in `reason`: {e}")

        infraction_list = await self.bot.api_client.get(
            "bot/infractions/expanded",
            params={"search": reason}
        )

        formatted_infraction_count = self.format_infraction_count(len(infraction_list))
        embed = discord.Embed(
            title=f"Infractions with matching context ({formatted_infraction_count} total)",
            colour=discord.Colour.orange()
        )
        if len(reason) > 500:
            reason = reason[:500] + "..."
        await self.send_infraction_list(ctx, embed, infraction_list, reason)

    # endregion
    # region: Search for infractions by given actor

    @infraction_group.command(name="by", aliases=("b",))
    async def search_by_actor(
        self,
        ctx: Context,
        actor: t.Literal["m", "me"] | UnambiguousUser,
        oldest_first: bool = False
    ) -> None:
        """
        Search for infractions made by `actor`.

        Use "m" or "me" as the `actor` to get infractions by author.

        Use "1" for `oldest_first` to send oldest infractions first.
        """
        if isinstance(actor, str):
            actor = ctx.author

        if oldest_first:
            ordering = "inserted_at"  # oldest infractions first
        else:
            ordering = "-inserted_at"  # newest infractions first

        infraction_list = await self.bot.api_client.get(
            "bot/infractions/expanded",
            params={
                "actor__id": str(actor.id),
                "ordering": ordering
            }
        )

        formatted_infraction_count = self.format_infraction_count(len(infraction_list))
        embed = discord.Embed(
            title=f"Infractions by {actor} ({formatted_infraction_count} total)",
            colour=discord.Colour.orange()
        )

        prefix = f"{actor.mention} - {actor.id}"
        await self.send_infraction_list(ctx, embed, infraction_list, prefix, ("actor",))

    # endregion
    # region: Utility functions

    @staticmethod
    def format_infraction_count(infraction_count: int) -> str:
        """
        Returns a string-formatted infraction count.

        API limits returned infractions to a maximum of 100, so if `infraction_count`
        is 100 then we return `"100+"`. Otherwise, return `str(infraction_count)`.
        """
        if infraction_count == 100:
            return "100+"
        return str(infraction_count)

    async def send_infraction_list(
        self,
        ctx: Context,
        embed: discord.Embed,
        infractions: t.Iterable[dict[str, t.Any]],
        prefix: str = "",
        ignore_fields: tuple[str, ...] = ()
    ) -> None:
        """Send a paginated embed of infractions for the specified user."""
        if not infractions:
            await ctx.send(":warning: No infractions could be found for that query.")
            return

        lines = [self.infraction_to_string(infraction, ignore_fields) for infraction in infractions]

        await LinePaginator.paginate(
            lines,
            ctx=ctx,
            embed=embed,
            prefix=f"{prefix}\n",
            empty=True,
            max_lines=3,
            max_size=1000
        )

    def infraction_to_string(self, infraction: dict[str, t.Any], ignore_fields: tuple[str, ...]) -> str:
        """Convert the infraction object to a string representation."""
        expires_at = infraction["expires_at"]
        inserted_at = infraction["inserted_at"]
        last_applied = infraction["last_applied"]
        jump_url = infraction["jump_url"]

        title = ""
        if "id" not in ignore_fields:
            title = f"**{self.format_infraction_title(infraction)}**"

        symbols = []
        if not infraction["hidden"] and infraction["dm_sent"] is False:
            symbols.append(FAILED_DM_SYMBOL)
        if infraction["hidden"]:
            symbols.append(HIDDEN_INFRACTION_SYMBOL)
        if inserted_at != infraction["last_applied"]:
            symbols.append(EDITED_DURATION_SYMBOL)
        symbols = " ".join(symbols)

        user_str = ""
        if "user" not in ignore_fields:
            user_str = "For " + self.format_user_from_record(infraction["user"])

        actor_str = ""
        if "actor" not in ignore_fields:
            actor_str = f"By <@{infraction['actor']['id']}>"

        issued = "Issued " + time.discord_timestamp(inserted_at)

        duration = ""
        if infraction["type"] not in NO_DURATION_INFRACTIONS:
            if expires_at is None:
                duration = "*Permanent*"
            else:
                duration = time.humanize_delta(last_applied, expires_at)
                if infraction["active"]:
                    duration = f"{duration} (Expires {time.format_relative(expires_at)})"
            duration = f"Duration: {duration}"

        if jump_url is None:
            # Infraction was issued prior to jump urls being stored in the database
            # or infraction was issued in ModMail category.
            context = f"**Context**: {infraction['reason'] or '*None*'}"
        else:
            context = f"**[Context]({jump_url})**: {infraction['reason'] or '*None*'}"

        return "\n".join(part for part in (title, symbols, user_str, actor_str, issued, duration, context) if part)

    def format_user_from_record(self, user: dict) -> str:
        """Create a formatted user string from its DB record."""
        if user_obj := self.bot.get_user(user["id"]):
            # The user is in the cache.
            return messages.format_user(user_obj)

        # Use the user data retrieved from the DB.
        name = escape_markdown(user["name"])
        return f"<@{user['id']}> ({name}#{user['discriminator']:04})"

    @staticmethod
    def format_infraction_title(infraction: Infraction) -> str:
        """Format the infraction title."""
        title = infraction["type"].replace("_", " ").title()
        if infraction["active"]:
            title = f"__Active__ {title}"
        return f"{title} #{infraction['id']}"

    # endregion

    # This cannot be static (must have a __func__ attribute).
    async def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators inside moderator channels to invoke the commands in this cog."""
        checks = [
            await commands.has_any_role(*constants.MODERATION_ROLES).predicate(ctx),
            is_mod_channel(ctx.channel)
        ]
        return all(checks)

    # This cannot be static (must have a __func__ attribute).
    async def cog_command_error(self, ctx: Context, error: commands.CommandError) -> None:
        """Handles errors for commands within this cog."""
        if isinstance(error, commands.BadUnionArgument):
            if discord.User in error.converters:
                await ctx.send(str(error.errors[0]))
                error.handled = True

        elif isinstance(error, InvalidInfractionError):
            if error.infraction_arg.isdigit():
                await ctx.send(f":x: Could not find an infraction with id `{error.infraction_arg}`.")
            else:
                await ctx.send(f":x: `{error.infraction_arg}` is not a valid integer infraction id.")
            error.handled = True


async def setup(bot: Bot) -> None:
    """Load the ModManagement cog."""
    await bot.add_cog(ModManagement(bot))
