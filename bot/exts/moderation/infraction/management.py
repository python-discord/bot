import textwrap
import typing as t

import disnake
from disnake.ext import commands
from disnake.ext.commands import Context
from disnake.utils import escape_markdown

from bot import constants
from bot.bot import Bot
from bot.converters import Expiry, Infraction, MemberOrUser, Snowflake, UnambiguousUser, allowed_strings
from bot.errors import InvalidInfraction
from bot.exts.moderation.infraction.infractions import Infractions
from bot.exts.moderation.modlog import ModLog
from bot.log import get_logger
from bot.pagination import LinePaginator
from bot.utils import messages, time
from bot.utils.channel import is_mod_channel
from bot.utils.members import get_or_fetch_member

log = get_logger(__name__)


class ModManagement(commands.Cog):
    """Management of infractions."""

    category = "Moderation"

    def __init__(self, bot: Bot):
        self.bot = bot

    @property
    def mod_log(self) -> ModLog:
        """Get currently loaded ModLog cog instance."""
        return self.bot.get_cog("ModLog")

    @property
    def infractions_cog(self) -> Infractions:
        """Get currently loaded Infractions cog instance."""
        return self.bot.get_cog("Infractions")

    # region: Edit infraction commands

    @commands.group(name='infraction', aliases=('infr', 'infractions', 'inf', 'i'), invoke_without_command=True)
    async def infraction_group(self, ctx: Context, infraction: Infraction = None) -> None:
        """
        Infraction manipulation commands.

        If `infraction` is passed then this command fetches that infraction. The `Infraction` converter
        supports 'l', 'last' and 'recent' to get the most recent infraction made by `ctx.author`.
        """
        if infraction is None:
            await ctx.send_help(ctx.command)
            return

        embed = disnake.Embed(
            title=f"Infraction #{infraction['id']}",
            colour=disnake.Colour.orange()
        )
        await self.send_infraction_list(ctx, embed, [infraction])

    @infraction_group.command(name="append", aliases=("amend", "add", "a"))
    async def infraction_append(
        self,
        ctx: Context,
        infraction: Infraction,
        duration: t.Union[Expiry, allowed_strings("p", "permanent"), None],   # noqa: F821
        *,
        reason: str = None
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
        """
        old_reason = infraction["reason"]

        if old_reason is not None and reason is not None:
            add_period = not old_reason.endswith((".", "!", "?"))
            reason = old_reason + (". " if add_period else " ") + reason

        await self.infraction_edit(ctx, infraction, duration, reason=reason)

    @infraction_group.command(name='edit', aliases=('e',))
    async def infraction_edit(
        self,
        ctx: Context,
        infraction: Infraction,
        duration: t.Union[Expiry, allowed_strings("p", "permanent"), None],   # noqa: F821
        *,
        reason: str = None
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
        """
        if duration is None and reason is None:
            # Unlike UserInputError, the error handler will show a specified message for BadArgument
            raise commands.BadArgument("Neither a new expiry nor a new reason was specified.")

        infraction_id = infraction["id"]

        request_data = {}
        confirm_messages = []
        log_text = ""

        if duration is not None and not infraction['active']:
            if (infr_type := infraction['type']) in ('note', 'warning'):
                await ctx.send(f":x: Cannot edit the expiration of a {infr_type}.")
            else:
                await ctx.send(":x: Cannot edit the expiration of an expired infraction.")
            return
        elif isinstance(duration, str):
            request_data['expires_at'] = None
            confirm_messages.append("marked as permanent")
        elif duration is not None:
            request_data['expires_at'] = duration.isoformat()
            expiry = time.format_with_duration(duration)
            confirm_messages.append(f"set to expire on {expiry}")
        else:
            confirm_messages.append("expiry unchanged")

        if reason:
            request_data['reason'] = reason
            confirm_messages.append("set a new reason")
            log_text += f"""
                Previous reason: {infraction['reason']}
                New reason: {reason}
            """.rstrip()
        else:
            confirm_messages.append("reason unchanged")

        # Update the infraction
        new_infraction = await self.bot.api_client.patch(
            f'bot/infractions/{infraction_id}',
            json=request_data,
        )

        # Re-schedule infraction if the expiration has been updated
        if 'expires_at' in request_data:
            # A scheduled task should only exist if the old infraction wasn't permanent
            if infraction['expires_at']:
                self.infractions_cog.scheduler.cancel(infraction_id)

            # If the infraction was not marked as permanent, schedule a new expiration task
            if request_data['expires_at']:
                self.infractions_cog.schedule_expiration(new_infraction)

            log_text += f"""
                Previous expiry: {time.until_expiration(infraction['expires_at'])}
                New expiry: {time.until_expiration(new_infraction['expires_at'])}
            """.rstrip()

        changes = ' & '.join(confirm_messages)
        await ctx.send(f":ok_hand: Updated infraction #{infraction_id}: {changes}")

        # Get information about the infraction's user
        user_id = new_infraction['user']
        user = await get_or_fetch_member(ctx.guild, user_id)

        if user:
            user_text = messages.format_user(user)
            thumbnail = user.display_avatar.url
        else:
            user_text = f"<@{user_id}>"
            thumbnail = None

        await self.mod_log.send_log_message(
            icon_url=constants.Icons.pencil,
            colour=disnake.Colour.og_blurple(),
            title="Infraction edited",
            thumbnail=thumbnail,
            text=textwrap.dedent(f"""
                Member: {user_text}
                Actor: <@{new_infraction['actor']}>
                Edited by: {ctx.message.author.mention}{log_text}
            """),
            footer=f"ID: {infraction_id}"
        )

    # endregion
    # region: Search infractions

    @infraction_group.group(name="search", aliases=('s',), invoke_without_command=True)
    async def infraction_search_group(self, ctx: Context, query: t.Union[UnambiguousUser, Snowflake, str]) -> None:
        """Searches for infractions in the database."""
        if isinstance(query, int):
            await self.search_user(ctx, disnake.Object(query))
        elif isinstance(query, str):
            await self.search_reason(ctx, query)
        else:
            await self.search_user(ctx, query)

    @infraction_search_group.command(name="user", aliases=("member", "userid"))
    async def search_user(self, ctx: Context, user: t.Union[MemberOrUser, disnake.Object]) -> None:
        """Search for infractions by member."""
        infraction_list = await self.bot.api_client.get(
            'bot/infractions/expanded',
            params={'user__id': str(user.id)}
        )

        if isinstance(user, (disnake.Member, disnake.User)):
            user_str = escape_markdown(str(user))
        else:
            if infraction_list:
                user = infraction_list[0]["user"]
                user_str = escape_markdown(user["name"]) + f"#{user['discriminator']:04}"
            else:
                user_str = str(user.id)

        formatted_infraction_count = self.format_infraction_count(len(infraction_list))
        embed = disnake.Embed(
            title=f"Infractions for {user_str} ({formatted_infraction_count} total)",
            colour=disnake.Colour.orange()
        )
        await self.send_infraction_list(ctx, embed, infraction_list)

    @infraction_search_group.command(name="reason", aliases=("match", "regex", "re"))
    async def search_reason(self, ctx: Context, reason: str) -> None:
        """Search for infractions by their reason. Use Re2 for matching."""
        infraction_list = await self.bot.api_client.get(
            'bot/infractions/expanded',
            params={'search': reason}
        )

        formatted_infraction_count = self.format_infraction_count(len(infraction_list))
        embed = disnake.Embed(
            title=f"Infractions matching `{reason}` ({formatted_infraction_count} total)",
            colour=disnake.Colour.orange()
        )
        await self.send_infraction_list(ctx, embed, infraction_list)

    # endregion
    # region: Search for infractions by given actor

    @infraction_group.command(name="by", aliases=("b",))
    async def search_by_actor(
        self,
        ctx: Context,
        actor: t.Union[t.Literal["m", "me"], UnambiguousUser],
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
            ordering = 'inserted_at'  # oldest infractions first
        else:
            ordering = '-inserted_at'  # newest infractions first

        infraction_list = await self.bot.api_client.get(
            'bot/infractions/expanded',
            params={
                'actor__id': str(actor.id),
                'ordering': ordering
            }
        )

        formatted_infraction_count = self.format_infraction_count(len(infraction_list))
        embed = disnake.Embed(
            title=f"Infractions by {actor} ({formatted_infraction_count} total)",
            colour=disnake.Colour.orange()
        )

        await self.send_infraction_list(ctx, embed, infraction_list)

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
        embed: disnake.Embed,
        infractions: t.Iterable[t.Dict[str, t.Any]]
    ) -> None:
        """Send a paginated embed of infractions for the specified user."""
        if not infractions:
            await ctx.send(":warning: No infractions could be found for that query.")
            return

        lines = tuple(
            self.infraction_to_string(infraction)
            for infraction in infractions
        )

        await LinePaginator.paginate(
            lines,
            ctx=ctx,
            embed=embed,
            empty=True,
            max_lines=3,
            max_size=1000
        )

    def infraction_to_string(self, infraction: t.Dict[str, t.Any]) -> str:
        """Convert the infraction object to a string representation."""
        active = infraction["active"]
        user = infraction["user"]
        expires_at = infraction["expires_at"]
        inserted_at = infraction["inserted_at"]
        created = time.discord_timestamp(inserted_at)
        dm_sent = infraction["dm_sent"]

        # Format the user string.
        if user_obj := self.bot.get_user(user["id"]):
            # The user is in the cache.
            user_str = messages.format_user(user_obj)
        else:
            # Use the user data retrieved from the DB.
            name = escape_markdown(user['name'])
            user_str = f"<@{user['id']}> ({name}#{user['discriminator']:04})"

        if active:
            remaining = time.until_expiration(expires_at)
        else:
            remaining = "Inactive"

        if expires_at is None:
            duration = "*Permanent*"
        else:
            duration = time.humanize_delta(inserted_at, expires_at)

        # Format `dm_sent`
        if dm_sent is None:
            dm_sent_text = "N/A"
        else:
            dm_sent_text = "Yes" if dm_sent else "No"

        lines = textwrap.dedent(f"""
            {"**===============**" if active else "==============="}
            Status: {"__**Active**__" if active else "Inactive"}
            User: {user_str}
            Type: **{infraction["type"]}**
            DM Sent: {dm_sent_text}
            Shadow: {infraction["hidden"]}
            Created: {created}
            Expires: {remaining}
            Duration: {duration}
            Actor: <@{infraction["actor"]["id"]}>
            ID: `{infraction["id"]}`
            Reason: {infraction["reason"] or "*None*"}
            {"**===============**" if active else "==============="}
        """)

        return lines.strip()

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
            if disnake.User in error.converters:
                await ctx.send(str(error.errors[0]))
                error.handled = True

        elif isinstance(error, InvalidInfraction):
            if error.infraction_arg.isdigit():
                await ctx.send(f":x: Could not find an infraction with id `{error.infraction_arg}`.")
            else:
                await ctx.send(f":x: `{error.infraction_arg}` is not a valid integer infraction id.")
            error.handled = True


def setup(bot: Bot) -> None:
    """Load the ModManagement cog."""
    bot.add_cog(ModManagement(bot))
