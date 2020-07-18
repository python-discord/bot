import logging

from discord import Colour, Embed
from discord.ext.commands import BadArgument, Cog, Context, group

from bot import constants
from bot.api import ResponseCodeError
from bot.bot import Bot
from bot.converters import ValidAllowDenyListType
from bot.pagination import LinePaginator
from bot.utils.checks import with_role_check

log = logging.getLogger(__name__)


class AllowDenyLists(Cog):
    """Commands for blacklisting and whitelisting things."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def _add_data(self, ctx: Context, allowed: bool, list_type: ValidAllowDenyListType, content: str) -> None:
        """Add an item to an allow or denylist."""
        payload = {
            'allowed': allowed,
            'type': list_type,
            'content': content,
        }
        allow_type = "whitelist" if allowed else "blacklist"

        # Try to add the item to the database
        try:
            item = await self.bot.api_client.post(
                "bot/allow_deny_lists",
                json=payload
            )
        except ResponseCodeError as e:
            if e.status == 500:
                await ctx.message.add_reaction("❌")
                raise BadArgument(
                    f"Unable to add the item to the {allow_type}. "
                    "The item probably already exists. Keep in mind that a "
                    "blacklist and a whitelist for the same item cannot co-exist, "
                    "and we do not permit any duplicates."
                )
            raise

        # Insert the item into the cache
        type_ = item.get("type")
        allowed = item.get("allowed")
        metadata = {
            "content": item.get("content"),
            "id": item.get("id"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }
        self.bot.allow_deny_list_cache.setdefault(f"{type_}.{allowed}", []).append(metadata)
        await ctx.message.add_reaction("✅")

    async def _delete_data(self, ctx: Context, allowed: bool, list_type: ValidAllowDenyListType, content: str) -> None:
        """Remove an item from an allow or denylist."""
        item = None

        for allow_list in self.bot.allow_deny_list_cache.get(f"{list_type}.{allowed}", []):
            if content == allow_list.get("content"):
                item = allow_list
                break

        if item is not None:
            await self.bot.api_client.delete(
                f"bot/allow_deny_lists/{item.get('id')}"
            )
            self.bot.allow_deny_list_cache[f"{list_type}.{allowed}"].remove(item)
            await ctx.message.add_reaction("✅")

    async def _list_all_data(self, ctx: Context, allowed: bool, list_type: ValidAllowDenyListType) -> None:
        """Paginate and display all items in an allow or denylist."""
        result = self.bot.allow_deny_list_cache.get(f"{list_type}.{allowed}", [])
        lines = sorted(f"• {item.get('content')}" for item in result)
        allowed_string = "Whitelisted" if allowed else "Blacklisted"
        embed = Embed(
            title=f"{allowed_string} {list_type.lower()} items ({len(result)} total)",
            colour=Colour.blue()
        )

        if result:
            await LinePaginator.paginate(lines, ctx, embed, max_lines=15, empty=False)
        else:
            embed.description = "Hmmm, seems like there's nothing here yet."
            await ctx.send(embed=embed)

    @group(aliases=("allowlist", "allow", "al", "wl"))
    async def whitelist(self, ctx: Context) -> None:
        """Group for whitelisting commands."""
        if not ctx.invoked_subcommand:
            await ctx.send_help(ctx.command)

    @group(aliases=("denylist", "deny", "bl", "dl"))
    async def blacklist(self, ctx: Context) -> None:
        """Group for blacklisting commands."""
        if not ctx.invoked_subcommand:
            await ctx.send_help(ctx.command)

    @whitelist.command(name="add", aliases=("a", "set"))
    async def allow_add(self, ctx: Context, list_type: ValidAllowDenyListType, content: str) -> None:
        """Add an item to the specified allowlist."""
        await self._add_data(ctx, True, list_type, content)

    @blacklist.command(name="add", aliases=("a", "set"))
    async def deny_add(self, ctx: Context, list_type: ValidAllowDenyListType, content: str) -> None:
        """Add an item to the specified denylist."""
        await self._add_data(ctx, False, list_type, content)

    @whitelist.command(name="remove", aliases=("delete", "rm",))
    async def allow_delete(self, ctx: Context, list_type: ValidAllowDenyListType, content: str) -> None:
        """Remove an item from the specified allowlist."""
        await self._delete_data(ctx, True, list_type, content)

    @blacklist.command(name="remove", aliases=("delete", "rm",))
    async def deny_delete(self, ctx: Context, list_type: ValidAllowDenyListType, content: str) -> None:
        """Remove an item from the specified denylist."""
        await self._delete_data(ctx, False, list_type, content)

    @whitelist.command(name="get", aliases=("list", "ls", "fetch", "show"))
    async def allow_get(self, ctx: Context, list_type: ValidAllowDenyListType) -> None:
        """Get the contents of a specified allowlist."""
        await self._list_all_data(ctx, True, list_type)

    @blacklist.command(name="get", aliases=("list", "ls", "fetch", "show"))
    async def deny_get(self, ctx: Context, list_type: ValidAllowDenyListType) -> None:
        """Get the contents of a specified denylist."""
        await self._list_all_data(ctx, False, list_type)

    def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators to invoke the commands in this cog."""
        checks = [
            with_role_check(ctx, *constants.MODERATION_ROLES),
        ]
        return all(checks)


def setup(bot: Bot) -> None:
    """Load the AllowDenyLists cog."""
    bot.add_cog(AllowDenyLists(bot))
