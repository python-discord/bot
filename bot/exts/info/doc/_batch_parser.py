from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from contextlib import suppress
from functools import partial
from operator import attrgetter
from typing import Dict, List, NamedTuple, Union

import discord
from bs4 import BeautifulSoup

import bot
from bot.constants import Channels
from bot.utils import scheduling
from . import _cog, doc_cache
from ._parsing import get_symbol_markdown

log = logging.getLogger(__name__)


class StaleInventoryNotifier:
    """Handle sending notifications about stale inventories through `DocItem`s to dev log."""

    def __init__(self):
        self._init_task = bot.instance.loop.create_task(self._init_channel())
        self._warned_urls = set()

    async def _init_channel(self) -> None:
        """Wait for guild and get channel."""
        await bot.instance.wait_until_guild_available()
        self._dev_log = bot.instance.get_channel(Channels.dev_log)

    async def send_warning(self, doc_item: _cog.DocItem) -> None:
        """Send a warning to dev log is one wasn't already sent for `item`'s url."""
        if doc_item.url not in self._warned_urls:
            self._warned_urls.add(doc_item.url)
            await self._init_task
            embed = discord.Embed(
                description=f"Doc item `{doc_item.symbol_id=}` present in loaded documentation inventories "
                            f"not found on [site]({doc_item.url}), inventories may need to be refreshed."
            )
            await self._dev_log.send(embed=embed)


class QueueItem(NamedTuple):
    """Contains a doc_item and the BeautifulSoup object needed to parse it."""

    doc_item: _cog.DocItem
    soup: BeautifulSoup

    def __eq__(self, other: Union[QueueItem, _cog.DocItem]):
        if isinstance(other, _cog.DocItem):
            return self.doc_item == other
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


class BatchParser:
    """
    Get the Markdown of all symbols on a page and send them to redis when a symbol is requested.

    DocItems are added through the `add_item` method which adds them to the `_page_doc_items` dict.
    `get_markdown` is used to fetch the Markdown; when this is used for the first time on a page,
    all of the symbols are queued to be parsed to avoid multiple web requests to the same page.
    """

    def __init__(self):
        self._queue: List[QueueItem] = []
        self._page_doc_items: Dict[str, List[_cog.DocItem]] = defaultdict(list)
        self._item_futures: Dict[_cog.DocItem, ParseResultFuture] = {}
        self._parse_task = None

        self.cleanup_futures_task = bot.instance.loop.create_task(self._cleanup_futures())

        self.stale_inventory_notifier = StaleInventoryNotifier()

    async def get_markdown(self, doc_item: _cog.DocItem) -> str:
        """
        Get the result Markdown of `doc_item`.

        If no symbols were fetched from `doc_item`s page before,
        the HTML has to be fetched and then all items from the page are put into the parse queue.

        Not safe to run while `self.clear` is running.
        """
        if doc_item not in self._item_futures:
            self._item_futures.update((item, ParseResultFuture()) for item in self._page_doc_items[doc_item.url])
            self._item_futures[doc_item].user_requested = True

            async with bot.instance.http_session.get(doc_item.url) as response:
                soup = await bot.instance.loop.run_in_executor(
                    None,
                    partial(BeautifulSoup, await response.text(encoding="utf8"), "lxml")
                )

            self._queue.extend(QueueItem(item, soup) for item in self._page_doc_items[doc_item.url])
            log.debug(f"Added items from {doc_item.url} to parse queue.")

            if self._parse_task is None:
                self._parse_task = asyncio.create_task(self._parse_queue())
        else:
            self._item_futures[doc_item].user_requested = True
        with suppress(ValueError):
            # If the item is not in the list then the item is already parsed or is being parsed
            self._move_to_front(doc_item)
        return await self._item_futures[doc_item]

    async def _parse_queue(self) -> None:
        """
        Parse all item from the queue, setting their result markdown on the futures and sending them to redis.

        The coroutine will run as long as the queue is not empty, resetting `self._parse_task` to None when finished.
        """
        log.trace("Starting queue parsing.")
        try:
            while self._queue:
                item, soup = self._queue.pop()
                try:
                    if (future := self._item_futures[item]).done():
                        # Some items are present in the inventories multiple times under different symbol names,
                        # if we already parsed an equal item, we can just skip it.
                        continue

                    markdown = await bot.instance.loop.run_in_executor(
                        None,
                        partial(get_symbol_markdown, soup, item),
                    )
                    if markdown is not None:
                        scheduling.create_task(doc_cache.set(item, markdown))
                    else:
                        scheduling.create_task(self.stale_inventory_notifier.send_warning(item))
                except Exception as e:
                    log.exception(f"Unexpected error when handling {item}")
                    future.set_exception(e)
                else:
                    future.set_result(markdown)
                await asyncio.sleep(0.1)
        finally:
            self._parse_task = None
            log.trace("Finished parsing queue.")

    def _move_to_front(self, item: Union[QueueItem, _cog.DocItem]) -> None:
        """Move `item` to the front of the parse queue."""
        # The parse queue stores soups along with the doc symbols in QueueItem objects,
        # in case we're moving a DocItem we have to get the associated QueueItem first and then move it.
        item_index = self._queue.index(item)
        queue_item = self._queue.pop(item_index)

        self._queue.append(queue_item)
        log.trace(f"Moved {item} to the front of the queue.")

    def add_item(self, doc_item: _cog.DocItem) -> None:
        """Map a DocItem to its page so that the symbol will be parsed once the page is requested."""
        self._page_doc_items[doc_item.url].append(doc_item)

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
        self._page_doc_items.clear()
        self._item_futures.clear()

    async def _cleanup_futures(self) -> None:
        """
        Clear old futures from internal results.

        After a future is set, we only need to wait for old requests to its associated `DocItem` to finish
        as all new requests will get the value from the redis cache in the cog first.
        Keeping them around for longer than a second is unnecessary and keeps the parsed Markdown strings alive.
        """
        while True:
            if not self._queue:
                current_time = time.time()
                for key, future in self._item_futures.copy().items():
                    if current_time - future.result_set_time > 5:
                        del self._item_futures[key]
            await asyncio.sleep(5)
