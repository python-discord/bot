from __future__ import annotations

import asyncio
import logging
import re
import sys
import time
from collections import defaultdict
from contextlib import suppress
from functools import partial
from operator import attrgetter
from types import SimpleNamespace
from typing import Dict, List, NamedTuple, Optional, Union

import discord
from bs4 import BeautifulSoup
from discord.ext import commands

from bot import instance as bot_instance
from bot.bot import Bot
from bot.constants import MODERATION_ROLES, RedirectOutput
from bot.converters import Inventory, PackageName, ValidURL
from bot.pagination import LinePaginator
from bot.utils.lock import lock
from bot.utils.messages import send_denial, wait_for_deletion
from bot.utils.scheduling import Scheduler
from ._inventory_parser import INVENTORY_DICT, fetch_inventory
from ._parsing import get_symbol_markdown
from ._redis_cache import DocRedisCache

log = logging.getLogger(__name__)

# symbols with a group contained here will get the group prefixed on duplicates
FORCE_PREFIX_GROUPS = (
    "2to3fixer",
    "token",
    "label",
    "pdbcommand",
    "term",
)
PRIORITY_PACKAGES = (
    "python",
)
WHITESPACE_AFTER_NEWLINES_RE = re.compile(r"(?<=\n\n)(\s+)")
NOT_FOUND_DELETE_DELAY = RedirectOutput.delete_delay
# Delay to wait before trying to reach a rescheduled inventory again, in minutes
FETCH_RESCHEDULE_DELAY = SimpleNamespace(first=2, repeated=5)

REFRESH_EVENT = asyncio.Event()
REFRESH_EVENT.set()
COMMAND_LOCK_SINGLETON = "inventory refresh"

doc_cache = DocRedisCache(namespace="Docs")


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


class QueueItem(NamedTuple):
    """Contains a symbol and the BeautifulSoup object needed to parse it."""

    symbol: DocItem
    soup: BeautifulSoup

    def __eq__(self, other: Union[QueueItem, DocItem]):
        if isinstance(other, DocItem):
            return self.symbol == other
        return NamedTuple.__eq__(self, other)


class ParseResultFuture(asyncio.Future):
    """
    Future with metadata for the parser class.

    `user_requested` is set by the parser when a Future is requested by an user and moved to the front,
    allowing the futures to only be waited for when clearing if they were user requested.

    `result_set_time` provides the time at which the future's result has been set,
    or -inf if the result hasn't been set yet
    """

    def __init__(self):
        super().__init__()
        self.user_requested = False
        self.result_set_time = float("inf")

    def set_result(self, result: str, /) -> None:
        """Set `self.result_set_time` to current time when the result is set."""
        self.result_set_time = time.time()
        super().set_result(result)


class CachedParser:
    """
    Get the symbol Markdown from pages with smarter caching.

    DocItems are added through the `add_item` method which adds them to the `_page_symbols` dict.
    `get_markdown` is used to fetch the Markdown; when this is used for the first time on a page,
    all of the symbols are queued to be parsed to avoid multiple web requests to the same page.
    """

    def __init__(self):
        self._queue: List[QueueItem] = []
        self._page_symbols: Dict[str, List[DocItem]] = defaultdict(list)
        self._item_futures: Dict[DocItem, ParseResultFuture] = {}
        self._parse_task = None

        self.cleanup_futures_task = bot_instance.loop.create_task(self._cleanup_futures())

    async def get_markdown(self, doc_item: DocItem) -> str:
        """
        Get the result Markdown of `doc_item`.

        If no symbols were fetched from `doc_item`s page before,
        the HTML has to be fetched before parsing can be queued.

        Not safe to run while `self.clear` is running.
        """
        if (symbols_to_queue := self._page_symbols.get(doc_item.url)) is not None:
            async with bot_instance.http_session.get(doc_item.url) as response:
                soup = BeautifulSoup(await response.text(encoding="utf8"), "lxml")

            self._queue.extend(QueueItem(symbol, soup) for symbol in symbols_to_queue)
            self._item_futures.update((symbol, ParseResultFuture()) for symbol in symbols_to_queue)
            del self._page_symbols[doc_item.url]
            log.debug(f"Added symbols from {doc_item.url} to parse queue.")

            if self._parse_task is None:
                self._parse_task = asyncio.create_task(self._parse_queue())

        with suppress(ValueError):
            # If the item is not in the list then the item is already parsed or is being parsed
            self._move_to_front(doc_item)
        self._item_futures[doc_item].user_requested = True
        return await self._item_futures[doc_item]

    async def _parse_queue(self) -> None:
        """
        Parse all item from the queue, setting associated events for symbols if present.

        The coroutine will run as long as the queue is not empty, resetting `self._parse_task` to None when finished.
        """
        log.trace("Starting queue parsing.")
        try:
            while self._queue:
                item, soup = self._queue.pop()
                try:
                    markdown = await bot_instance.loop.run_in_executor(
                        None,
                        partial(get_symbol_markdown, soup, item),
                    )
                    if markdown is not None:
                        await doc_cache.set(item, markdown)
                except Exception:
                    log.exception(f"Unexpected error when handling {item}")
                else:
                    if (future := self._item_futures.get(item)) is not None:
                        future.set_result(markdown)
                await asyncio.sleep(0.1)
        finally:
            self._parse_task = None
            log.trace("Finished parsing queue.")

    def _move_to_front(self, item: Union[QueueItem, DocItem]) -> None:
        """Move `item` to the front of the parse queue."""
        # The parse queue stores soups along with the doc symbols in QueueItem objects,
        # in case we're moving a DocItem we have to get the associated QueueItem first and then move it.
        item_index = self._queue.index(item)
        queue_item = self._queue.pop(item_index)

        self._queue.append(queue_item)

    def add_item(self, doc_item: DocItem) -> None:
        """Map a DocItem to its page so that the symbol will be parsed once the page is requested."""
        self._page_symbols[doc_item.url].append(doc_item)

    async def clear(self) -> None:
        """
        Clear all internal symbol data.

        All currently requested items are waited to be parsed before clearing.
        """
        for future in filter(attrgetter("user_requested"), self._item_futures.values()):
            await future
        if self._parse_task is not None:
            self._parse_task.cancel()
        self._queue.clear()
        self._page_symbols.clear()
        self._item_futures.clear()

    async def _cleanup_futures(self) -> None:
        """
        Clear old futures from internal results.

        After a future is set, we only need to wait for old requests to its associated DocItem to finish
        as all new requests will get the value from the redis cache in the cog first.
        Keeping them around for longer than a second is unnecessary and keeps the parsed Markdown strings alive.
        """
        while True:
            current_time = time.time()
            for key, future in self._item_futures.copy().items():
                if current_time - future.result_set_time > 5:
                    del self._item_futures[key]
            await asyncio.sleep(5)


class DocCog(commands.Cog):
    """A set of commands for querying & displaying documentation."""

    def __init__(self, bot: Bot):
        self.base_urls = {}
        self.bot = bot
        self.doc_symbols: Dict[str, DocItem] = {}
        self.item_fetcher = CachedParser()
        self.renamed_symbols = set()

        self.inventory_scheduler = Scheduler(self.__class__.__name__)
        self.scheduled_inventories = set()

        self.bot.loop.create_task(self.init_refresh_inventory())

    @lock("doc", COMMAND_LOCK_SINGLETON, raise_error=True)
    async def init_refresh_inventory(self) -> None:
        """Refresh documentation inventory on cog initialization."""
        await self.bot.wait_until_guild_available()
        await self.refresh_inventory()

    async def update_single(self, api_package_name: str, base_url: str, package: INVENTORY_DICT) -> None:
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
                while (original_symbol := self.doc_symbols.get(symbol)) is not None:
                    replaced_symbol_name = self.ensure_unique_symbol_name(
                        api_package_name,
                        group_name,
                        original_symbol,
                        symbol,
                    )
                    if replaced_symbol_name is None:
                        break
                    else:
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
    ) -> Optional[INVENTORY_DICT]:
        """
        Update the cog's inventory, or reschedule this method to execute again if the remote inventory unreachable.

        The first attempt is rescheduled to execute in `FETCH_RESCHEDULE_DELAY.first` minutes, the subsequent attempts
        in `FETCH_RESCHEDULE_DELAY.repeated` minutes.
        """
        package = await fetch_inventory(inventory_url)

        if not package:
            if inventory_url not in self.scheduled_inventories:
                delay = FETCH_RESCHEDULE_DELAY.first
            else:
                delay = FETCH_RESCHEDULE_DELAY.repeated
            log.info(f"Failed to fetch inventory; attempting again in {delay} minutes.")
            self.inventory_scheduler.schedule_later(
                delay*60,
                api_package_name,
                self.update_or_reschedule_inventory(api_package_name, base_url, inventory_url)
            )
            self.scheduled_inventories.add(api_package_name)
            return

        self.scheduled_inventories.discard(api_package_name)
        await self.update_single(api_package_name, base_url, package)

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
            self.renamed_symbols.add(symbol_name)
            return f"{group_name}.{symbol_name}"

        # The existing symbol with which the current symbol conflicts should have a group prefix.
        # It currently doesn't have the group prefix because it's only added once there's a conflict.
        elif (original_symbol_group := original_item.group) in FORCE_PREFIX_GROUPS:
            overridden_symbol = f"{original_symbol_group}.{symbol_name}"
            if overridden_symbol in self.doc_symbols:
                # If there's still a conflict, prefix with package name.
                overridden_symbol = f"{original_item.package}.{overridden_symbol}"

            self.doc_symbols[overridden_symbol] = original_item
            self.renamed_symbols.add(overridden_symbol)

        elif package_name in PRIORITY_PACKAGES:
            overridden_symbol = f"{original_item.package}.{symbol_name}"
            if overridden_symbol in self.doc_symbols:
                # If there's still a conflict, add the symbol's group in the middle.
                overridden_symbol = f"{original_item.package}.{original_item.group}.{symbol_name}"

            self.doc_symbols[overridden_symbol] = original_item
            self.renamed_symbols.add(overridden_symbol)

        # If we can't specially handle the symbol through its group or package,
        # fall back to prepending its package name to the front.
        else:
            if symbol_name.startswith(package_name):
                # If the symbol already starts with the package name, insert the group name after it.
                split_symbol_name = symbol_name.split(".", maxsplit=1)
                split_symbol_name.insert(1, group_name)
                overridden_symbol = ".".join(split_symbol_name)
            else:
                overridden_symbol = f"{package_name}.{symbol_name}"
            self.renamed_symbols.add(overridden_symbol)
            return overridden_symbol

    async def refresh_inventory(self) -> None:
        """Refresh internal documentation inventory."""
        REFRESH_EVENT.clear()
        log.debug("Refreshing documentation inventory...")
        self.inventory_scheduler.cancel_all()

        # Clear the old base URLS and doc symbols to ensure
        # that we start from a fresh local dataset.
        # Also, reset the cache used for fetching documentation.
        self.base_urls.clear()
        self.doc_symbols.clear()
        self.renamed_symbols.clear()
        self.scheduled_inventories.clear()
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
        REFRESH_EVENT.set()

    async def get_symbol_embed(self, symbol: str) -> Optional[discord.Embed]:
        """
        Attempt to scrape and fetch the data for the given `symbol`, and build an embed from its contents.

        If the symbol is known, an Embed with documentation about it is returned.

        First check the DocRedisCache before querying the cog's `CachedParser`,
        if not present also create a redis entry for the symbol.
        """
        log.trace(f"Building embed for symbol `{symbol}`")
        if not REFRESH_EVENT.is_set():
            log.debug("Waiting for inventories to be refreshed before processing item.")
            await REFRESH_EVENT.wait()

        symbol_info = self.doc_symbols.get(symbol)
        if symbol_info is None:
            log.debug("Symbol does not exist.")
            return None
        self.bot.stats.incr(f"doc_fetches.{symbol_info.package.lower()}")

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
        embed.set_footer(
            text=", ".join(renamed for renamed in self.renamed_symbols - {symbol} if renamed.endswith(f".{symbol}"))
        )
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

        await self.update_single(package_name, base_url, inventory_dict)
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
    async def clear_cache_command(self, ctx: commands.Context, package_name: PackageName) -> None:
        """Clear the persistent redis cache for `package`."""
        if await doc_cache.delete(package_name):
            await ctx.send(f"Successfully cleared the cache for `{package_name}`.")
        else:
            await ctx.send("No keys matching the package found.")

    def cog_unload(self) -> None:
        """Clear scheduled inventories, queued symbols and cleanup task on cog unload."""
        self.inventory_scheduler.cancel_all()
        self.item_fetcher.cleanup_futures_task.cancel()
        asyncio.create_task(self.item_fetcher.clear())
