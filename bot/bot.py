import asyncio
from collections import defaultdict

import aiohttp
from botcore import BotBase
from botcore.utils import scheduling
from sentry_sdk import push_scope

from bot import constants, exts
from bot.log import get_logger

log = get_logger('bot')


class StartupError(Exception):
    """Exception class for startup errors."""

    def __init__(self, base: Exception):
        super().__init__()
        self.exception = base


class Bot(BotBase):
    """A subclass of `botcore.BotBase` that implements bot-specific functions."""

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.filter_list_cache = defaultdict(dict)

    async def ping_services(self) -> None:
        """A helper to make sure all the services the bot relies on are available on startup."""
        # Connect Site/API
        attempts = 0
        while True:
            try:
                log.info(f"Attempting site connection: {attempts + 1}/{constants.URLs.connect_max_retries}")
                await self.api_client.get("healthcheck")
                break

            except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError):
                attempts += 1
                if attempts == constants.URLs.connect_max_retries:
                    raise
                await asyncio.sleep(constants.URLs.connect_cooldown)

    def insert_item_into_filter_list_cache(self, item: dict[str, str]) -> None:
        """Add an item to the bots filter_list_cache."""
        type_ = item["type"]
        allowed = item["allowed"]
        content = item["content"]

        self.filter_list_cache[f"{type_}.{allowed}"][content] = {
            "id": item["id"],
            "comment": item["comment"],
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
        }

    async def cache_filter_list_data(self) -> None:
        """Cache all the data in the FilterList on the site."""
        full_cache = await self.api_client.get('bot/filter-lists')

        for item in full_cache:
            self.insert_item_into_filter_list_cache(item)

    async def setup_hook(self) -> None:
        """Default Async initialisation method for Discord.py."""
        await super().setup_hook()

        if self.redis_session.closed:
            # If the RedisSession was somehow closed, we try to reconnect it
            # here. Normally, this shouldn't happen.
            await self.redis_session.connect()

        # Build the FilterList cache
        await self.cache_filter_list_data()

        scheduling.create_task(self.load_extensions(exts))

    async def on_error(self, event: str, *args, **kwargs) -> None:
        """Log errors raised in event listeners rather than printing them to stderr."""
        self.stats.incr(f"errors.event.{event}")

        with push_scope() as scope:
            scope.set_tag("event", event)
            scope.set_extra("args", args)
            scope.set_extra("kwargs", kwargs)

            log.exception(f"Unhandled exception in {event}.")
