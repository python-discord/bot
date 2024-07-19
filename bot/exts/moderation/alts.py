import gettext

import discord
from discord.ext import commands
from pydis_core.site_api import ResponseCodeError
from pydis_core.utils.members import get_or_fetch_member

from bot import constants
from bot.bot import Bot
from bot.converters import UnambiguousMemberOrUser
from bot.log import get_logger
from bot.pagination import LinePaginator
from bot.utils.channel import is_mod_channel
from bot.utils.time import discord_timestamp

log = get_logger(__name__)


class AlternateAccounts(commands.Cog):
    """A cog used to track a user's alternative accounts across Discord."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @staticmethod
    def error_text_from_error(error: ResponseCodeError) -> str:
        """Format the error into a user-facing message."""
        if resp_json := error.response_json:
            errors = ", ".join(
                resp_json.get("non_field_errors", []) +
                resp_json.get("source", []) +
                resp_json.get("target", []) +
                resp_json.get("detail", [])
            )
            if errors:
                return gettext.ngettext("Error from site: ", "Errors from site: ", len(errors)) + errors
            return str(error.response_json)
        return error.response_text

    async def alts_to_string(self, alts: list[dict]) -> list[str]:
        """Convert a list of alts to a list of string representations."""
        lines = []
        guild = self.bot.get_guild(self.bot.guild_id)
        for idx, alt in enumerate(alts):
            alt_obj = await get_or_fetch_member(guild, alt["target"])
            alt_name = str(alt_obj) if alt_obj else alt["target"]
            created_at = discord_timestamp(alt["created_at"])
            updated_at = discord_timestamp(alt["updated_at"])

            edited = f" edited on {updated_at}\n" if "edited" in alt else "\n"
            num_alts = len(alt["alts"])
            lines.append(
                f"**Association #{idx} - {alt_name}**\n"
                f"<@{alt['target']}> - {alt['target']}\n"
                f"Issued by: <@{alt['actor']}> ({alt['actor']}) on {created_at}{edited}"
                f"Context: {alt['context']}\n"
                f"<@{alt['target']}> has {num_alts} associated {gettext.ngettext('account', 'accounts', num_alts)}"
            )
        return lines

    @commands.group(name="association", aliases=("alt", "assoc"), invoke_without_command=True)
    async def association_group(
        self,
        ctx: commands.Context,
        user_1: UnambiguousMemberOrUser,
        user_2: UnambiguousMemberOrUser,
        *,
        context: str,
    ) -> None:
        """
        Alternate accounts commands.

        When called directly marks the two users given as alt accounts.
        The context as to why they are believed to be alt accounts must be given.
        """
        if user_1.bot or user_2.bot:
            await ctx.send(":x: Cannot mark bots as alts")
            return

        try:
            await self.bot.api_client.post(
                f"bot/users/{user_1.id}/alts",
                json={"target": user_2.id, "actor": ctx.author.id, "context": context},
            )
        except ResponseCodeError as e:
            error = self.error_text_from_error(e)
            await ctx.send(f":x: {error}")
            return
        await ctx.send(f"✅ {user_1.mention} and {user_2.mention} successfully marked as alts.")

    @association_group.command(name="edit", aliases=("e",))
    async def edit_association_command(
        self,
        ctx: commands.Context,
        user_1: UnambiguousMemberOrUser,
        user_2: UnambiguousMemberOrUser,
        *,
        context: str,
    ) -> None:
        """Edit the context of an association between two users."""
        try:
            await self.bot.api_client.patch(
                f"bot/users/{user_1.id}/alts",
                json={"target": user_2.id, "context": context},
            )
        except ResponseCodeError as e:
            error = self.error_text_from_error(e)
            await ctx.send(f":x: {error}")
            return
        await ctx.send(f"✅ Context for association between {user_1.mention} and {user_2.mention} updated.")

    @association_group.command(name="remove", aliases=("r",))
    async def alt_remove_command(
        self,
        ctx: commands.Context,
        user_1: UnambiguousMemberOrUser,
        user_2: UnambiguousMemberOrUser,
    ) -> None:
        """Remove the alt association between the two users."""
        try:
            await self.bot.api_client.delete(
                f"bot/users/{user_1.id}/alts",
                json=user_2.id,
            )
        except ResponseCodeError as e:
            error = self.error_text_from_error(e)
            await ctx.send(f":x: {error}")
            return
        await ctx.send(f"✅ {user_1.mention} and {user_2.mention} are no longer marked as alts.")

    @association_group.command(name="info", root_aliases=("alts",))
    async def alt_info_command(
        self,
        ctx: commands.Context,
        user: UnambiguousMemberOrUser,
    ) -> None:
        """Output a list of known alts of this user, and the reasons as to why they are believed to be alts."""
        try:
            resp = await self.bot.api_client.get(f"bot/users/{user.id}")
        except ResponseCodeError as e:
            if e.status == 404:
                await ctx.send(f":x: {user.mention} not found in site database")
                return
            raise
        alts = resp["alts"]
        if not alts:
            await ctx.send(f":x: No known alts for {user}")
            return

        embed = discord.Embed(
            title=f"Associated accounts for {user} ({len(alts)} total)",
            colour=discord.Colour.orange(),
        )
        lines = await self.alts_to_string(alts)
        await LinePaginator.paginate(
            lines,
            ctx=ctx,
            embed=embed,
            empty=True,
            max_lines=3,
            max_size=1000,
        )

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Only allow moderators inside moderator channels to invoke the commands in this cog."""
        checks = [
            await commands.has_any_role(*constants.MODERATION_ROLES).predicate(ctx),
            is_mod_channel(ctx.channel)
        ]
        return all(checks)

async def setup(bot: Bot) -> None:
    """Load the AlternateAccounts cog."""
    await bot.add_cog(AlternateAccounts(bot))
