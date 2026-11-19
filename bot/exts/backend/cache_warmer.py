import asyncio
import itertools
import time
from collections import deque
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

import discord
from discord import TextChannel, Thread
from discord.ext.commands import Cog
from pydis_core.utils import scheduling

from bot.bot import Bot
from bot.constants import Guild
from bot.log import get_logger

log = get_logger(__name__)

# How far back to load messages. This is longer than the hour that `cleanban` looks back, so that the oldest
# message in the cache is older than the limit of the clean, which is what makes the clean use the cache.
WARM_WINDOW = timedelta(hours=1, minutes=30)
CONCURRENT_CHANNELS = 4


def merge_into_cache(cache: deque[discord.Message], messages: Iterable[discord.Message]) -> int:
    """
    Add older `messages` to the start of the message `cache`, keeping it in chronological order.

    Messages which are already in the cache, or which are newer than its oldest message, are skipped as the cache
    has been filled with them by gateway events. The cache never has messages dropped to make room, so if there
    isn't room for all of `messages` only the newest of them are added.

    Returns the number of messages added.
    """
    capacity = cache.maxlen - len(cache) if cache.maxlen is not None else None
    cached_ids = {message.id for message in cache}
    oldest_cached = cache[0].id if cache else None

    candidates = sorted(
        {
            message.id: message
            for message in messages
            if message.id not in cached_ids and (oldest_cached is None or message.id < oldest_cached)
        }.values(),
        key=lambda message: message.id,
        reverse=True,
    )
    if capacity is not None:
        candidates = candidates[:capacity]

    # Each message is added to the left of the previous one, so adding the newest first leaves the oldest leftmost.
    cache.extendleft(candidates)
    return len(candidates)


class MessageCacheWarmer(Cog):
    """Loads recent messages into the message cache on startup, so cleaning doesn't need to fetch them."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.task: asyncio.Task | None = None

    async def cog_load(self) -> None:
        """Start warming the cache in the background."""
        self.task = scheduling.create_task(self.warm_cache())

    async def cog_unload(self) -> None:
        """Stop warming the cache if it is still running."""
        if self.task is not None:
            self.task.cancel()

    async def _fetch_channel(self, channel: TextChannel | Thread, after: datetime, limit: int) -> list[discord.Message]:
        """Fetch the messages sent in the channel after the given time."""
        try:
            return [message async for message in channel.history(limit=limit, after=after)]
        except discord.Forbidden:
            log.debug("Not allowed to read the history of %s (%d) to warm the cache.", channel, channel.id)
        except discord.HTTPException:
            log.exception("Failed to fetch the history of %s (%d) to warm the cache.", channel, channel.id)
        return []

    async def warm_cache(self) -> None:
        """Fetch the recent messages of the channels which are cleaned by default, and add them to the cache."""
        await self.bot.wait_until_guild_available()

        cache = self.bot._connection._messages
        if not cache or cache.maxlen is None:
            log.info("The message cache is disabled or unbounded, so it won't be warmed.")
            return

        guild = self.bot.get_guild(Guild.id)
        # The same channels as a clean of all channels, which skips non-public channels for speed.
        channels = [
            channel for channel in itertools.chain(guild.channels, guild.threads)
            if isinstance(channel, TextChannel | Thread) and channel.permissions_for(guild.default_role).view_channel
        ]

        log.info("Warming the message cache from %d channels.", len(channels))
        start = time.monotonic()
        after = datetime.now(tz=UTC) - WARM_WINDOW
        semaphore = asyncio.Semaphore(CONCURRENT_CHANNELS)

        async def fetch(channel: TextChannel | Thread) -> list[discord.Message]:
            async with semaphore:
                return await self._fetch_channel(channel, after, cache.maxlen)

        fetched = await asyncio.gather(*(fetch(channel) for channel in channels))

        # This has no awaits, so no gateway events can add messages to the cache while it is merged.
        added = merge_into_cache(cache, itertools.chain.from_iterable(fetched))
        log.info("Added %d messages to the message cache in %.1f seconds.", added, time.monotonic() - start)


async def setup(bot: Bot) -> None:
    """Load the MessageCacheWarmer cog."""
    await bot.add_cog(MessageCacheWarmer(bot))
