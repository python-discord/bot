import logging
from typing import Optional

from discord import Colour, Embed
from discord.ext.commands import BadArgument, Cog, Context, IDConverter, group, has_any_role

from bot import constants
from bot.api import ResponseCodeError
from bot.bot import Bot
from bot.converters import ValidDiscordServerInvite, ValidFilterListType
from bot.pagination import LinePaginator

log = logging.getLogger(__name__)


class FilterLists(Cog):
    """Commands for blacklisting and whitelisting things."""

    methods_with_filterlist_types = [
        "allow_add",
        "allow_delete",
        "allow_get",
        "deny_add",
        "deny_delete",
        "deny_get",
    ]

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.bot.loop.create_task(self._amend_docstrings())

    async def _amend_docstrings(self) -> None:
        """Add the valid FilterList types to the docstrings, so they'll appear in !help invocations."""
        await self.bot.wait_until_guild_available()

        # Add valid filterlist types to the docstrings
        valid_types = await ValidFilterListType.get_valid_types(self.bot)
        valid_types = [f"`{type_.lower()}`" for type_ in valid_types]

        for method_name in self.methods_with_filterlist_types:
            command = getattr(self, method_name)
            command.help = (
                f"{command.help}\n\nValid **list_type** values are {', '.join(valid_types)}."
            )

    async def _add_data(
        self,
        ctx: Context,
        allowed: bool,
        list_type: ValidFilterListType,
        content: str,
        comment: Optional[str] = None,
    ) -> None:
        """Add an item to a filterlist."""
        allow_type = "whitelist" if allowed else "blacklist"

        # If this is a server invite, we gotta validate it.
        if list_type == "GUILD_INVITE":
            guild_data = await self._validate_guild_invite(ctx, content)
            content = guild_data.get("id")

            # Unless the user has specified another comment, let's
            # use the server name as the comment so that the list
            # of guild IDs will be more easily readable when we
            # display it.
            if not comment:
                comment = guild_data.get("name")

        # If it's a file format, let's make sure it has a leading dot.
        elif list_type == "FILE_FORMAT" and not content.startswith("."):
            content = f".{content}"

        # Try to add the item to the database
        log.trace(f"Trying to add the {content} item to the {list_type} {allow_type}")
        payload = {
            "allowed": allowed,
            "type": list_type,
            "content": content,
            "comment": comment,
        }

        try:
            item = await self.bot.api_client.post(
                "bot/filter-lists",
                json=payload
            )
        except ResponseCodeError as e:
            if e.status == 400:
                await ctx.message.add_reaction("❌")
                log.debug(
                    f"{ctx.author} tried to add data to a {allow_type}, but the API returned 400, "
                    "probably because the request violated the UniqueConstraint."
                )
                raise BadArgument(
                    f"Unable to add the item to the {allow_type}. "
                    "The item probably already exists. Keep in mind that a "
                    "blacklist and a whitelist for the same item cannot co-exist, "
                    "and we do not permit any duplicates."
                )
            raise

        # Insert the item into the cache
        self.bot.insert_item_into_filter_list_cache(item)
        await ctx.message.add_reaction("✅")

    async def _delete_data(self, ctx: Context, allowed: bool, list_type: ValidFilterListType, content: str) -> None:
        """Remove an item from a filterlist."""
        allow_type = "whitelist" if allowed else "blacklist"

        # If this is a server invite, we need to convert it.
        if list_type == "GUILD_INVITE" and not IDConverter()._get_id_match(content):
            guild_data = await self._validate_guild_invite(ctx, content)
            content = guild_data.get("id")

        # If it's a file format, let's make sure it has a leading dot.
        elif list_type == "FILE_FORMAT" and not content.startswith("."):
            content = f".{content}"

        # Find the content and delete it.
        log.trace(f"Trying to delete the {content} item from the {list_type} {allow_type}")
        item = self.bot.filter_list_cache[f"{list_type}.{allowed}"].get(content)

        if item is not None:
            try:
                await self.bot.api_client.delete(
                    f"bot/filter-lists/{item['id']}"
                )
                del self.bot.filter_list_cache[f"{list_type}.{allowed}"][content]
                await ctx.message.add_reaction("✅")
            except ResponseCodeError as e:
                log.debug(
                    f"{ctx.author} tried to delete an item with the id {item['id']}, but "
                    f"the API raised an unexpected error: {e}"
                )
                await ctx.message.add_reaction("❌")
        else:
            await ctx.message.add_reaction("❌")

    async def _list_all_data(self, ctx: Context, allowed: bool, list_type: ValidFilterListType) -> None:
        """Paginate and display all items in a filterlist."""
        allow_type = "whitelist" if allowed else "blacklist"
        result = self.bot.filter_list_cache[f"{list_type}.{allowed}"]

        # Build a list of lines we want to show in the paginator
        lines = []
        for content, metadata in result.items():
            line = f"• `{content}`"

            if comment := metadata.get("comment"):
                line += f" - {comment}"

            lines.append(line)
        lines = sorted(lines)

        # Build the embed
        list_type_plural = list_type.lower().replace("_", " ").title() + "s"
        embed = Embed(
            title=f"{allow_type.title()}ed {list_type_plural} ({len(result)} total)",
            colour=Colour.blue()
        )
        log.trace(f"Trying to list {len(result)} items from the {list_type.lower()} {allow_type}")

        if result:
            await LinePaginator.paginate(lines, ctx, embed, max_lines=15, empty=False)
        else:
            embed.description = "Hmmm, seems like there's nothing here yet."
            await ctx.send(embed=embed)
            await ctx.message.add_reaction("❌")

    async def _sync_data(self, ctx: Context) -> None:
        """Syncs the filterlists with the API."""
        try:
            log.trace("Attempting to sync FilterList cache with data from the API.")
            await self.bot.cache_filter_list_data()
            await ctx.message.add_reaction("✅")
        except ResponseCodeError as e:
            log.debug(
                f"{ctx.author} tried to sync FilterList cache data but "
                f"the API raised an unexpected error: {e}"
            )
            await ctx.message.add_reaction("❌")

    @staticmethod
    async def _validate_guild_invite(ctx: Context, invite: str) -> dict:
        """
        Validates a guild invite, and returns the guild info as a dict.

        Will raise a BadArgument if the guild invite is invalid.
        """
        log.trace(f"Attempting to validate whether or not {invite} is a guild invite.")
        validator = ValidDiscordServerInvite()
        guild_data = await validator.convert(ctx, invite)

        # If we make it this far without raising a BadArgument, the invite is
        # valid. Let's return a dict of guild information.
        log.trace(f"{invite} validated as server invite. Converting to ID.")
        return guild_data

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
    async def allow_add(
        self,
        ctx: Context,
        list_type: ValidFilterListType,
        content: str,
        *,
        comment: Optional[str] = None,
    ) -> None:
        """Add an item to the specified allowlist."""
        await self._add_data(ctx, True, list_type, content, comment)

    @blacklist.command(name="add", aliases=("a", "set"))
    async def deny_add(
        self,
        ctx: Context,
        list_type: ValidFilterListType,
        content: str,
        *,
        comment: Optional[str] = None,
    ) -> None:
        """Add an item to the specified denylist."""
        await self._add_data(ctx, False, list_type, content, comment)

    @whitelist.command(name="remove", aliases=("delete", "rm",))
    async def allow_delete(self, ctx: Context, list_type: ValidFilterListType, content: str) -> None:
        """Remove an item from the specified allowlist."""
        await self._delete_data(ctx, True, list_type, content)

    @blacklist.command(name="remove", aliases=("delete", "rm",))
    async def deny_delete(self, ctx: Context, list_type: ValidFilterListType, content: str) -> None:
        """Remove an item from the specified denylist."""
        await self._delete_data(ctx, False, list_type, content)

    @whitelist.command(name="get", aliases=("list", "ls", "fetch", "show"))
    async def allow_get(self, ctx: Context, list_type: ValidFilterListType) -> None:
        """Get the contents of a specified allowlist."""
        await self._list_all_data(ctx, True, list_type)

    @blacklist.command(name="get", aliases=("list", "ls", "fetch", "show"))
    async def deny_get(self, ctx: Context, list_type: ValidFilterListType) -> None:
        """Get the contents of a specified denylist."""
        await self._list_all_data(ctx, False, list_type)

    @whitelist.command(name="sync", aliases=("s",))
    async def allow_sync(self, ctx: Context) -> None:
        """Syncs both allowlists and denylists with the API."""
        await self._sync_data(ctx)

    @blacklist.command(name="sync", aliases=("s",))
    async def deny_sync(self, ctx: Context) -> None:
        """Syncs both allowlists and denylists with the API."""
        await self._sync_data(ctx)

    async def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators to invoke the commands in this cog."""
        return await has_any_role(*constants.MODERATION_ROLES).predicate(ctx)


def setup(bot: Bot) -> None:
    """Load the FilterLists cog."""
    bot.add_cog(FilterLists(bot))
