import logging
import textwrap
import typing as t
from datetime import datetime

import discord
from discord.ext import commands
from discord.ext.commands import Context
from discord.utils import escape_markdown

from bot import constants
from bot.bot import Bot
from bot.converters import Expiry, Snowflake, UserMention, allowed_strings, proxy_user
from bot.exts.moderation.infraction.infractions import Infractions
from bot.exts.moderation.modlog import ModLog
from bot.pagination import LinePaginator
from bot.utils import messages, time
from bot.utils.checks import in_whitelist_check

log = logging.getLogger(__name__)


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

    @commands.group(name='infraction', aliases=('infr', 'infractions', 'inf'), invoke_without_command=True)
    async def infraction_group(self, ctx: Context) -> None:
        """Infraction manipulation commands."""
        await ctx.send_help(ctx.command)

    @infraction_group.command(name="append", aliases=("amend", "add"))
    async def infraction_append(
        self,
        ctx: Context,
        infraction_id: t.Union[int, allowed_strings("l", "last", "recent")],  # noqa: F821
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
        """
        if isinstance(infraction_id, str):
            old_infraction = await self.get_latest_infraction(ctx.author.id)

            if old_infraction is None:
                await ctx.send(
                    ":x: Couldn't find most recent infraction; you have never given an infraction."
                )
                return

            infraction_id = old_infraction["id"]

        else:
            old_infraction = await self.bot.api_client.get(f"bot/infractions/{infraction_id}")

        reason = f"{old_infraction['reason']} **Edit:** {reason}"

        await ctx.invoke(self.infraction_edit, infraction_id=infraction_id, duration=duration, reason=reason)

    @infraction_group.command(name='edit')
    async def infraction_edit(
        self,
        ctx: Context,
        infraction_id: t.Union[int, allowed_strings("l", "last", "recent")],  # noqa: F821
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

        # Retrieve the previous infraction for its information.
        if isinstance(infraction_id, str):
            old_infraction = await self.get_latest_infraction(ctx.author.id)

            if old_infraction is None:
                await ctx.send(
                    ":x: Couldn't find most recent infraction; you have never given an infraction."
                )
                return

            infraction_id = old_infraction["id"]

        else:
            old_infraction = await self.bot.api_client.get(f"bot/infractions/{infraction_id}")

        request_data = {}
        confirm_messages = []
        log_text = ""

        if duration is not None and not old_infraction['active']:
            if reason is None:
                await ctx.send(":x: Cannot edit the expiration of an expired infraction.")
                return
            confirm_messages.append("expiry unchanged (infraction already expired)")
        elif isinstance(duration, str):
            request_data['expires_at'] = None
            confirm_messages.append("marked as permanent")
        elif duration is not None:
            request_data['expires_at'] = duration.isoformat()
            expiry = time.format_infraction_with_duration(request_data['expires_at'])
            confirm_messages.append(f"set to expire on {expiry}")
        else:
            confirm_messages.append("expiry unchanged")

        if reason:
            request_data['reason'] = reason
            confirm_messages.append("set a new reason")
            log_text += f"""
                Previous reason: {old_infraction['reason']}
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
            if old_infraction['expires_at']:
                self.infractions_cog.scheduler.cancel(new_infraction['id'])

            # If the infraction was not marked as permanent, schedule a new expiration task
            if request_data['expires_at']:
                self.infractions_cog.schedule_expiration(new_infraction)

            log_text += f"""
                Previous expiry: {old_infraction['expires_at'] or "Permanent"}
                New expiry: {new_infraction['expires_at'] or "Permanent"}
            """.rstrip()

        changes = ' & '.join(confirm_messages)
        await ctx.send(f":ok_hand: Updated infraction #{infraction_id}: {changes}")

        # Get information about the infraction's user
        user_id = new_infraction['user']
        user = ctx.guild.get_member(user_id)

        if user:
            user_text = messages.format_user(user)
            thumbnail = user.avatar_url_as(static_format="png")
        else:
            user_text = f"<@{user_id}>"
            thumbnail = None

        await self.mod_log.send_log_message(
            icon_url=constants.Icons.pencil,
            colour=discord.Colour.blurple(),
            title="Infraction edited",
            thumbnail=thumbnail,
            text=textwrap.dedent(f"""
                Member: {user_text}
                Actor: <@{new_infraction['actor']}>
                Edited by: {ctx.message.author.mention}{log_text}
            """)
        )

    # endregion
    # region: Search infractions

    @infraction_group.group(name="search", invoke_without_command=True)
    async def infraction_search_group(self, ctx: Context, query: t.Union[UserMention, Snowflake, str]) -> None:
        """Searches for infractions in the database."""
        if isinstance(query, int):
            await ctx.invoke(self.search_user, discord.Object(query))
        else:
            await ctx.invoke(self.search_reason, query)

    @infraction_search_group.command(name="user", aliases=("member", "id"))
    async def search_user(self, ctx: Context, user: t.Union[discord.User, proxy_user]) -> None:
        """Search for infractions by member."""
        infraction_list = await self.bot.api_client.get(
            'bot/infractions/expanded',
            params={'user__id': str(user.id)}
        )

        user = self.bot.get_user(user.id)
        if not user and infraction_list:
            # Use the user data retrieved from the DB for the username.
            user = infraction_list[0]
            user = escape_markdown(user["name"]) + f"#{user['discriminator']:04}"

        embed = discord.Embed(
            title=f"Infractions for {user} ({len(infraction_list)} total)",
            colour=discord.Colour.orange()
        )
        await self.send_infraction_list(ctx, embed, infraction_list)

    @infraction_search_group.command(name="reason", aliases=("match", "regex", "re"))
    async def search_reason(self, ctx: Context, reason: str) -> None:
        """Search for infractions by their reason. Use Re2 for matching."""
        infraction_list = await self.bot.api_client.get(
            'bot/infractions/expanded',
            params={'search': reason}
        )
        embed = discord.Embed(
            title=f"Infractions matching `{reason}` ({len(infraction_list)} total)",
            colour=discord.Colour.orange()
        )
        await self.send_infraction_list(ctx, embed, infraction_list)

    # endregion
    # region: Utility functions

    async def send_infraction_list(
        self,
        ctx: Context,
        embed: discord.Embed,
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
        created = time.format_infraction(infraction["inserted_at"])

        # Format the user string.
        if user_obj := self.bot.get_user(user["id"]):
            # The user is in the cache.
            user_str = messages.format_user(user_obj)
        else:
            # Use the user data retrieved from the DB.
            name = escape_markdown(user['name'])
            user_str = f"<@{user['id']}> ({name}#{user['discriminator']:04})"

        if active:
            remaining = time.until_expiration(expires_at) or "Expired"
        else:
            remaining = "Inactive"

        if expires_at is None:
            expires = "*Permanent*"
        else:
            date_from = datetime.strptime(created, time.INFRACTION_FORMAT)
            expires = time.format_infraction_with_duration(expires_at, date_from)

        lines = textwrap.dedent(f"""
            {"**===============**" if active else "==============="}
            Status: {"__**Active**__" if active else "Inactive"}
            User: {user_str}
            Type: **{infraction["type"]}**
            Shadow: {infraction["hidden"]}
            Created: {created}
            Expires: {expires}
            Remaining: {remaining}
            Actor: <@{infraction["actor"]["id"]}>
            ID: `{infraction["id"]}`
            Reason: {infraction["reason"] or "*None*"}
            {"**===============**" if active else "==============="}
        """)

        return lines.strip()

    async def get_latest_infraction(self, actor: int) -> t.Optional[dict]:
        """Obtains the latest infraction from an actor."""
        params = {
            "actor__id": actor,
            "ordering": "-inserted_at"
        }

        infractions = await self.bot.api_client.get("bot/infractions", params=params)

        if infractions:
            return infractions[0]

        return None

    # endregion

    # This cannot be static (must have a __func__ attribute).
    async def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators inside moderator channels to invoke the commands in this cog."""
        checks = [
            await commands.has_any_role(*constants.MODERATION_ROLES).predicate(ctx),
            in_whitelist_check(
                ctx,
                channels=constants.MODERATION_CHANNELS,
                categories=[constants.Categories.modmail],
                redirect=None,
                fail_silently=True,
            )
        ]
        return all(checks)

    # This cannot be static (must have a __func__ attribute).
    async def cog_command_error(self, ctx: Context, error: Exception) -> None:
        """Send a notification to the invoking context on a Union failure."""
        if isinstance(error, commands.BadUnionArgument):
            if discord.User in error.converters:
                await ctx.send(str(error.errors[0]))
                error.handled = True


def setup(bot: Bot) -> None:
    """Load the ModManagement cog."""
    bot.add_cog(ModManagement(bot))
