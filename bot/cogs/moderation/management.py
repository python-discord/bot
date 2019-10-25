import asyncio
import logging
import textwrap
import typing as t

import discord
from discord.ext import commands
from discord.ext.commands import Context

from bot import constants
from bot.converters import InfractionSearchQuery
from bot.pagination import LinePaginator
from bot.utils import time
from bot.utils.checks import in_channel_check, with_role_check
from . import utils
from .infractions import Infractions
from .modlog import ModLog

log = logging.getLogger(__name__)

UserConverter = t.Union[discord.User, utils.proxy_user]


def permanent_duration(expires_at: str) -> str:
    """Only allow an expiration to be 'permanent' if it is a string."""
    expires_at = expires_at.lower()
    if expires_at != "permanent":
        raise commands.BadArgument
    else:
        return expires_at


class ModManagement(commands.Cog):
    """Management of infractions."""

    category = "Moderation"

    def __init__(self, bot: commands.Bot):
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
        await ctx.invoke(self.bot.get_command("help"), "infraction")

    @infraction_group.command(name='edit')
    async def infraction_edit(
        self,
        ctx: Context,
        infraction_id: int,
        duration: t.Union[utils.Expiry, permanent_duration, None],
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

        Use "permanent" to mark the infraction as permanent. Alternatively, an ISO 8601 timestamp
        can be provided for the duration.
        """
        if duration is None and reason is None:
            # Unlike UserInputError, the error handler will show a specified message for BadArgument
            raise commands.BadArgument("Neither a new expiry nor a new reason was specified.")

        # Retrieve the previous infraction for its information.
        old_infraction = await self.bot.api_client.get(f'bot/infractions/{infraction_id}')

        request_data = {}
        confirm_messages = []
        log_text = ""

        if duration == "permanent":
            request_data['expires_at'] = None
            confirm_messages.append("marked as permanent")
        elif duration is not None:
            request_data['expires_at'] = duration.isoformat()
            expiry = duration.strftime(time.INFRACTION_FORMAT)
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
            self.infractions_cog.cancel_task(new_infraction['id'])
            loop = asyncio.get_event_loop()
            self.infractions_cog.schedule_task(loop, new_infraction['id'], new_infraction)

            log_text += f"""
                Previous expiry: {old_infraction['expires_at'] or "Permanent"}
                New expiry: {new_infraction['expires_at'] or "Permanent"}
            """.rstrip()

        await ctx.send(f":ok_hand: Updated infraction: {' & '.join(confirm_messages)}")

        # Get information about the infraction's user
        user_id = new_infraction['user']
        user = ctx.guild.get_member(user_id)

        if user:
            user_text = f"{user.mention} (`{user.id}`)"
            thumbnail = user.avatar_url_as(static_format="png")
        else:
            user_text = f"`{user_id}`"
            thumbnail = None

        # The infraction's actor
        actor_id = new_infraction['actor']
        actor = ctx.guild.get_member(actor_id) or f"`{actor_id}`"

        await self.mod_log.send_log_message(
            icon_url=constants.Icons.pencil,
            colour=discord.Colour.blurple(),
            title="Infraction edited",
            thumbnail=thumbnail,
            text=textwrap.dedent(f"""
                Member: {user_text}
                Actor: {actor}
                Edited by: {ctx.message.author}{log_text}
            """)
        )

    # endregion
    # region: Search infractions

    @infraction_group.group(name="search", invoke_without_command=True)
    async def infraction_search_group(self, ctx: Context, query: InfractionSearchQuery) -> None:
        """Searches for infractions in the database."""
        if isinstance(query, discord.User):
            await ctx.invoke(self.search_user, query)
        else:
            await ctx.invoke(self.search_reason, query)

    @infraction_search_group.command(name="user", aliases=("member", "id"))
    async def search_user(self, ctx: Context, user: UserConverter) -> None:
        """Search for infractions by member."""
        infraction_list = await self.bot.api_client.get(
            'bot/infractions',
            params={'user__id': str(user.id)}
        )
        embed = discord.Embed(
            title=f"Infractions for {user} ({len(infraction_list)} total)",
            colour=discord.Colour.orange()
        )
        await self.send_infraction_list(ctx, embed, infraction_list)

    @infraction_search_group.command(name="reason", aliases=("match", "regex", "re"))
    async def search_reason(self, ctx: Context, reason: str) -> None:
        """Search for infractions by their reason. Use Re2 for matching."""
        infraction_list = await self.bot.api_client.get(
            'bot/infractions',
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
        infractions: t.Iterable[utils.Infraction]
    ) -> None:
        """Send a paginated embed of infractions for the specified user."""
        if not infractions:
            await ctx.send(f":warning: No infractions could be found for that query.")
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

    def infraction_to_string(self, infraction: utils.Infraction) -> str:
        """Convert the infraction object to a string representation."""
        actor_id = infraction["actor"]
        guild = self.bot.get_guild(constants.Guild.id)
        actor = guild.get_member(actor_id)
        active = infraction["active"]
        user_id = infraction["user"]
        hidden = infraction["hidden"]
        created = time.format_infraction(infraction["inserted_at"])
        if infraction["expires_at"] is None:
            expires = "*Permanent*"
        else:
            expires = time.format_infraction(infraction["expires_at"])

        lines = textwrap.dedent(f"""
            {"**===============**" if active else "==============="}
            Status: {"__**Active**__" if active else "Inactive"}
            User: {self.bot.get_user(user_id)} (`{user_id}`)
            Type: **{infraction["type"]}**
            Shadow: {hidden}
            Reason: {infraction["reason"] or "*None*"}
            Created: {created}
            Expires: {expires}
            Actor: {actor.mention if actor else actor_id}
            ID: `{infraction["id"]}`
            {"**===============**" if active else "==============="}
        """)

        return lines.strip()

    # endregion

    # This cannot be static (must have a __func__ attribute).
    def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators from moderator channels to invoke the commands in this cog."""
        checks = [
            with_role_check(ctx, *constants.MODERATION_ROLES),
            in_channel_check(ctx, *constants.MODERATION_CHANNELS)
        ]
        return all(checks)

    # This cannot be static (must have a __func__ attribute).
    async def cog_command_error(self, ctx: Context, error: Exception) -> None:
        """Send a notification to the invoking context on a Union failure."""
        if isinstance(error, commands.BadUnionArgument):
            if discord.User in error.converters:
                await ctx.send(str(error.errors[0]))
                error.handled = True
