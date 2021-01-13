from __future__ import annotations

import asyncio
import logging
import sys
import textwrap
from collections import defaultdict
from contextlib import suppress
from types import SimpleNamespace
from typing import Dict, NamedTuple, Optional

import discord
from discord.ext import commands

from bot.bot import Bot
from bot.constants import MODERATION_ROLES, RedirectOutput
from bot.converters import Inventory, PackageName, ValidURL
from bot.pagination import LinePaginator
from bot.utils.lock import lock
from bot.utils.messages import send_denial, wait_for_deletion
from bot.utils.scheduling import Scheduler
from . import PRIORITY_PACKAGES, doc_cache
from ._batch_parser import BatchParser
from ._inventory_parser import INVENTORY_DICT, fetch_inventory

log = logging.getLogger(__name__)

# symbols with a group contained here will get the group prefixed on duplicates
FORCE_PREFIX_GROUPS = (
    "2to3fixer",
    "token",
    "label",
    "pdbcommand",
    "term",
)
NOT_FOUND_DELETE_DELAY = RedirectOutput.delete_delay
# Delay to wait before trying to reach a rescheduled inventory again, in minutes
FETCH_RESCHEDULE_DELAY = SimpleNamespace(first=2, repeated=5)

COMMAND_LOCK_SINGLETON = "inventory refresh"


class DocItem(NamedTuple):
    """Holds inventory symbol information."""

    package: str
    group: str
    base_url: str
    relative_url_path: str
    symbol_id: str

    @property
    def url(self) -> str:
        """Return the absolute url to the symbol."""
        return self.base_url + self.relative_url_path


class DocCog(commands.Cog):
    """A set of commands for querying & displaying documentation."""

    def __init__(self, bot: Bot):
        self.base_urls = {}
        self.bot = bot
        self.doc_symbols: Dict[str, DocItem] = {}
        self.item_fetcher = BatchParser()
        self.renamed_symbols = defaultdict(list)

        self.inventory_scheduler = Scheduler(self.__class__.__name__)
        self.inventory_reschedule_attempts = defaultdict(int)

        self.refresh_event = asyncio.Event()
        self.refresh_event.set()
        self.init_refresh_task = self.bot.loop.create_task(self.init_refresh_inventory())

    @lock("doc", COMMAND_LOCK_SINGLETON, raise_error=True)
    async def init_refresh_inventory(self) -> None:
        """Refresh documentation inventory on cog initialization."""
        await self.bot.wait_until_guild_available()
        await self.refresh_inventory()

    def update_single(self, api_package_name: str, base_url: str, package: INVENTORY_DICT) -> None:
        """
        Rebuild the inventory for a single package.

        Where:
            * `package_name` is the package name to use, appears in the log
            * `base_url` is the root documentation URL for the specified package, used to build
                absolute paths that link to specific symbols
            * `inventory_url` is the absolute URL to the intersphinx inventory.
        """
        self.base_urls[api_package_name] = base_url

        for group, items in package.items():
            for symbol, relative_doc_url in items:

                # e.g. get 'class' from 'py:class'
                group_name = group.split(":")[1]
                if (original_symbol := self.doc_symbols.get(symbol)) is not None:
                    replaced_symbol_name = self.ensure_unique_symbol_name(
                        api_package_name,
                        group_name,
                        original_symbol,
                        symbol,
                    )
                    if replaced_symbol_name is not None:
                        symbol = replaced_symbol_name

                relative_url_path, _, symbol_id = relative_doc_url.partition("#")
                # Intern fields that have shared content so we're not storing unique strings for every object
                symbol_item = DocItem(
                    api_package_name,
                    sys.intern(group_name),
                    base_url,
                    sys.intern(relative_url_path),
                    symbol_id
                )
                self.doc_symbols[symbol] = symbol_item
                self.item_fetcher.add_item(symbol_item)

        log.trace(f"Fetched inventory for {api_package_name}.")

    async def update_or_reschedule_inventory(
            self,
            api_package_name: str,
            base_url: str,
            inventory_url: str
    ) -> None:
        """
        Update the cog's inventory, or reschedule this method to execute again if the remote inventory unreachable.

        The first attempt is rescheduled to execute in `FETCH_RESCHEDULE_DELAY.first` minutes, the subsequent attempts
        in `FETCH_RESCHEDULE_DELAY.repeated` minutes.
        """
        package = await fetch_inventory(inventory_url)

        if not package:
            attempt = self.inventory_reschedule_attempts[package]
            self.inventory_reschedule_attempts[package] += 1
            if attempt == 0:
                delay = FETCH_RESCHEDULE_DELAY.first
            else:
                delay = FETCH_RESCHEDULE_DELAY.repeated
            log.info(f"Failed to fetch inventory; attempting again in {delay} minutes.")
            self.inventory_scheduler.schedule_later(
                delay*60,
                (attempt, api_package_name),
                self.update_or_reschedule_inventory(api_package_name, base_url, inventory_url)
            )
        else:
            self.update_single(api_package_name, base_url, package)

    def ensure_unique_symbol_name(
            self,
            package_name: str,
            group_name: str,
            original_item: DocItem,
            symbol_name: str
    ) -> Optional[str]:
        """
        Ensure `symbol_name` doesn't overwrite an another symbol in `doc_symbols`.

        Should only be called with symbol names that already have a conflict in `doc_symbols`.

        If None is returned, space was created for `symbol_name` in `doc_symbols` instead of
        the symbol name being changed.
        """
        # Certain groups are added as prefixes to disambiguate the symbols.
        if group_name in FORCE_PREFIX_GROUPS:
            new_symbol = f"{group_name}.{symbol_name}"
            if new_symbol in self.doc_symbols:
                # If there's still a conflict, prefix with package name.
                new_symbol = f"{package_name}.{new_symbol}"
            self.renamed_symbols[symbol_name].append(new_symbol)
            return new_symbol

        # The existing symbol with which the current symbol conflicts should have a group prefix.
        # It currently doesn't have the group prefix because it's only added once there's a conflict.
        elif (original_symbol_group := original_item.group) in FORCE_PREFIX_GROUPS:
            overridden_symbol = f"{original_symbol_group}.{symbol_name}"
            if overridden_symbol in self.doc_symbols:
                # If there's still a conflict, prefix with package name.
                overridden_symbol = f"{original_item.package}.{overridden_symbol}"

            self.doc_symbols[overridden_symbol] = original_item
            self.renamed_symbols[symbol_name].append(overridden_symbol)

        elif package_name in PRIORITY_PACKAGES:
            overridden_symbol = f"{original_item.package}.{symbol_name}"
            if overridden_symbol in self.doc_symbols:
                # If there's still a conflict, add the symbol's group in the middle.
                overridden_symbol = f"{original_item.package}.{original_item.group}.{symbol_name}"

            self.doc_symbols[overridden_symbol] = original_item
            self.renamed_symbols[symbol_name].append(overridden_symbol)

        # If we can't specially handle the symbol through its group or package,
        # fall back to prepending its package name to the front.
        else:
            new_symbol = f"{package_name}.{symbol_name}"
            if new_symbol in self.doc_symbols:
                # If there's still a conflict, add the symbol's group in the middle.
                new_symbol = f"{package_name}.{group_name}.{symbol_name}"
            self.renamed_symbols[symbol_name].append(new_symbol)
            return new_symbol

    async def refresh_inventory(self) -> None:
        """Refresh internal documentation inventory."""
        self.refresh_event.clear()
        log.debug("Refreshing documentation inventory...")
        self.inventory_scheduler.cancel_all()
        self.inventory_reschedule_attempts.clear()

        # Clear the old base URLS and doc symbols to ensure
        # that we start from a fresh local dataset.
        # Also, reset the cache used for fetching documentation.
        self.base_urls.clear()
        self.doc_symbols.clear()
        self.renamed_symbols.clear()
        await self.item_fetcher.clear()

        # Run all coroutines concurrently - since each of them performs an HTTP
        # request, this speeds up fetching the inventory data heavily.
        coros = [
            self.update_or_reschedule_inventory(
                package["package"], package["base_url"], package["inventory_url"]
            ) for package in await self.bot.api_client.get('bot/documentation-links')
        ]
        await asyncio.gather(*coros)
        log.debug("Finished inventory refresh.")
        self.refresh_event.set()

    async def get_symbol_embed(self, symbol: str) -> Optional[discord.Embed]:
        """
        Attempt to scrape and fetch the data for the given `symbol`, and build an embed from its contents.

        If the symbol is known, an Embed with documentation about it is returned.

        First check the DocRedisCache before querying the cog's `BatchParser`.
        """
        log.trace(f"Building embed for symbol `{symbol}`")
        if not self.refresh_event.is_set():
            log.debug("Waiting for inventories to be refreshed before processing item.")
            await self.refresh_event.wait()

        symbol_info = self.doc_symbols.get(symbol)
        if symbol_info is None:
            log.debug("Symbol does not exist.")
            return None
        self.bot.stats.incr(f"doc_fetches.{symbol_info.package}")

        markdown = await doc_cache.get(symbol_info)
        if markdown is None:
            log.debug(f"Redis cache miss for symbol `{symbol}`.")
            markdown = await self.item_fetcher.get_markdown(symbol_info)
            if markdown is not None:
                await doc_cache.set(symbol_info, markdown)
            else:
                markdown = "Unable to parse the requested symbol."

        embed = discord.Embed(
            title=discord.utils.escape_markdown(symbol),
            url=f"{symbol_info.url}#{symbol_info.symbol_id}",
            description=markdown
        )
        # Show all symbols with the same name that were renamed in the footer.
        if symbol in self.renamed_symbols:
            renamed_symbols = ', '.join(self.renamed_symbols[symbol])
            footer_text = f"Moved: {textwrap.shorten(renamed_symbols, 100, placeholder=' ...')}"
        else:
            footer_text = ""
        embed.set_footer(text=footer_text)
        return embed

    @commands.group(name='docs', aliases=('doc', 'd'), invoke_without_command=True)
    async def docs_group(self, ctx: commands.Context, *, symbol: Optional[str]) -> None:
        """Look up documentation for Python symbols."""
        await self.get_command(ctx, symbol=symbol)

    @docs_group.command(name='getdoc', aliases=('g',))
    async def get_command(self, ctx: commands.Context, *, symbol: Optional[str]) -> None:
        """
        Return a documentation embed for a given symbol.

        If no symbol is given, return a list of all available inventories.

        Examples:
            !docs
            !docs aiohttp
            !docs aiohttp.ClientSession
            !docs getdoc aiohttp.ClientSession
        """
        if not symbol:
            inventory_embed = discord.Embed(
                title=f"All inventories (`{len(self.base_urls)}` total)",
                colour=discord.Colour.blue()
            )

            lines = sorted(f"• [`{name}`]({url})" for name, url in self.base_urls.items())
            if self.base_urls:
                await LinePaginator.paginate(lines, ctx, inventory_embed, max_size=400, empty=False)

            else:
                inventory_embed.description = "Hmmm, seems like there's nothing here yet."
                await ctx.send(embed=inventory_embed)

        else:
            symbol = symbol.strip("`")
            # Fetching documentation for a symbol (at least for the first time, since
            # caching is used) takes quite some time, so let's send typing to indicate
            # that we got the command, but are still working on it.
            async with ctx.typing():
                doc_embed = await self.get_symbol_embed(symbol)

            if doc_embed is None:
                error_message = await send_denial(ctx, "No documentation found for the requested symbol.")
                await wait_for_deletion(error_message, (ctx.author.id,), timeout=NOT_FOUND_DELETE_DELAY)
                with suppress(discord.NotFound):
                    await ctx.message.delete()
                with suppress(discord.NotFound):
                    await error_message.delete()
            else:
                msg = await ctx.send(embed=doc_embed)
                await wait_for_deletion(msg, (ctx.author.id,))

    @docs_group.command(name='setdoc', aliases=('s',))
    @commands.has_any_role(*MODERATION_ROLES)
    @lock("doc", COMMAND_LOCK_SINGLETON, raise_error=True)
    async def set_command(
        self,
        ctx: commands.Context,
        package_name: PackageName,
        base_url: ValidURL,
        inventory: Inventory,
    ) -> None:
        """
        Adds a new documentation metadata object to the site's database.

        The database will update the object, should an existing item with the specified `package_name` already exist.

        Example:
            !docs setdoc \
                    python \
                    https://docs.python.org/3/ \
                    https://docs.python.org/3/objects.inv
        """
        inventory_url, inventory_dict = inventory
        body = {
            'package': package_name,
            'base_url': base_url,
            'inventory_url': inventory_url
        }
        await self.bot.api_client.post('bot/documentation-links', json=body)

        log.info(
            f"User @{ctx.author} ({ctx.author.id}) added a new documentation package:\n"
            + "\n".join(f"{key}: {value}" for key, value in body.items())
        )

        self.update_single(package_name, base_url, inventory_dict)
        await ctx.send(f"Added the package `{package_name}` to the database and refreshed the inventory.")

    @docs_group.command(name='deletedoc', aliases=('removedoc', 'rm', 'd'))
    @commands.has_any_role(*MODERATION_ROLES)
    @lock("doc", COMMAND_LOCK_SINGLETON, raise_error=True)
    async def delete_command(self, ctx: commands.Context, package_name: PackageName) -> None:
        """
        Removes the specified package from the database.

        Example:
            !docs deletedoc aiohttp
        """
        await self.bot.api_client.delete(f'bot/documentation-links/{package_name}')

        async with ctx.typing():
            # Rebuild the inventory to ensure that everything
            # that was from this package is properly deleted.
            await self.refresh_inventory()
            await doc_cache.delete(package_name)
        await ctx.send(f"Successfully deleted `{package_name}` and refreshed the inventory.")

    @docs_group.command(name="refreshdoc", aliases=("rfsh", "r"))
    @commands.has_any_role(*MODERATION_ROLES)
    @lock("doc", COMMAND_LOCK_SINGLETON, raise_error=True)
    async def refresh_command(self, ctx: commands.Context) -> None:
        """Refresh inventories and show the difference."""
        old_inventories = set(self.base_urls)
        with ctx.typing():
            await self.refresh_inventory()
        new_inventories = set(self.base_urls)

        if added := ", ".join(new_inventories - old_inventories):
            added = "+ " + added

        if removed := ", ".join(old_inventories - new_inventories):
            removed = "- " + removed

        embed = discord.Embed(
            title="Inventories refreshed",
            description=f"```diff\n{added}\n{removed}```" if added or removed else ""
        )
        await ctx.send(embed=embed)

    @docs_group.command(name="cleardoccache")
    @commands.has_any_role(*MODERATION_ROLES)
    @lock("doc", COMMAND_LOCK_SINGLETON, raise_error=True)
    async def clear_cache_command(self, ctx: commands.Context, package_name: PackageName) -> None:
        """Clear the persistent redis cache for `package`."""
        if await doc_cache.delete(package_name):
            await self.refresh_inventory()
            await ctx.send(f"Successfully cleared the cache for `{package_name}` and refreshed the inventories.")
        else:
            await ctx.send("No keys matching the package found.")

    def cog_unload(self) -> None:
        """Clear scheduled inventories, queued symbols and cleanup task on cog unload."""
        self.inventory_scheduler.cancel_all()
        self.item_fetcher.cleanup_futures_task.cancel()
        self.init_refresh_task.cancel()
        asyncio.create_task(self.item_fetcher.clear())
