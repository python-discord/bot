import asyncio
import datetime
import logging
import re
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from typing import Optional

import aiohttp
import discord
from discord import Color, Embed, Message, Object, errors
from discord.ext.commands import BadArgument, Bot, Context

from bot.constants import BigBrother as BigBrotherConfig, Guild as GuildConfig
from bot.pagination import LinePaginator
from bot.utils import messages
from bot.utils.time import time_since

log = logging.getLogger(__name__)

URL_RE = re.compile(r"(https?://[^\s]+)")


def proxy_user(user_id: str) -> Object:
    try:
        user_id = int(user_id)
    except ValueError:
        raise BadArgument
    user = Object(user_id)
    user.mention = user.id
    user.display_name = f"<@{user.id}>"
    user.avatar_url_as = lambda static_format: None
    user.bot = False
    return user


class WatchChannel(ABC):
    """
    Base class for WatchChannels

    Abstracts the basic functionality for watchchannels in
    a granular manner to allow for easy overwritting of
    methods in the child class.
    """

    @abstractmethod
    def __init__(self, bot: Bot) -> None:
        """
        abstractmethod for __init__ which should still be called with super().

        Note: Some of the attributes below need to be overwritten in the
        __init__ of the child after the super().__init__(*args, **kwargs)
        call.
        """
        self.bot = bot

        # These attributes need to be overwritten in the child class
        self.destination = None  # Channels.big_brother_logs
        self.webhook_id = None  # Webhooks.big_brother
        self.api_endpoint = None  # 'bot/infractions'
        self.api_default_params = None  # {'active': 'true', 'type': 'watch'}

        # These attributes can be left as they are in the child class
        self._consume_task = None
        self.watched_users = defaultdict(dict)
        self.message_queue = defaultdict(lambda: defaultdict(deque))
        self.consumption_queue = {}
        self.retries = 5
        self.retry_delay = 10
        self.channel = None
        self.webhook = None
        self.message_history = [None, None, 0]

        self._start = self.bot.loop.create_task(self.start_watchchannel())

    @property
    def consuming_messages(self) -> bool:
        """Checks if a consumption task is currently running."""
        if self._consume_task is None:
            return False

        if self._consume_task.done():
            exc = self._consume_task.exception()
            if exc:
                self.log.exception(
                    f"{self.__class__.__name__} consume task has failed with:",
                    exc_info=exc
                )
            return False

        return True

    async def start_watchchannel(self) -> None:
        """Retrieves watched users from the API."""
        await self.bot.wait_until_ready()

        if await self.initialize_channel() and await self.fetch_user_cache():
            self.log.trace(f"Started the {self.__class__.__name__} WatchChannel")
        else:
            self.log.error(f"Failed to start the {self.__class__.__name__} WatchChannel")

    async def initialize_channel(self) -> bool:
        """
        Checks if channel and webhook are set; if not, tries to initialize them.

        Since the internal channel cache may not be available directly after `ready`,
        this function will retry to get the channel a number of times. If both the
        channel and webhook were initialized successfully. this function will return
        `True`.
        """
        if self.channel is None:
            for attempt in range(1, self.retries + 1):
                self.channel = self.bot.get_channel(self.destination)

                if self.channel is None:
                    self.log.error(f"Failed to get the {self.__class__.__name__} channel; cannot watch users")
                    if attempt < self.initialization_retries:
                        self.log.error(f"Attempt {attempt}/{self.retries}; Retrying in {self.retry_delay} seconds...")
                        await asyncio.sleep(self.retry_delay)
                else:
                    self.log.trace(f"Retrieved the TextChannel for {self.__class__.__name__}")
                    break
            else:
                self.log.error(f"Cannot get channel with id `{self.destination}`; cannot watch users")
                return False

        if self.webhook is None:
            self.webhook = await self.bot.get_webhook_info(self.webhook_id)  # This is `fetch_webhook` in current
            if self.webhook is None:
                self.log.error(f"Cannot get webhook with id `{self.webhook_id}`; cannot watch users")
                return False
            self.log.trace(f"Retrieved the webhook for {self.__class__.__name__}")

        self.log.trace(f"WatchChannel for {self.__class__.__name__} is fully initialized")
        return True

    async def fetch_user_cache(self) -> bool:
        """
        Fetches watched users from the API and updates the watched user cache accordingly.

        This function returns `True` if the update succeeded.
        """
        try:
            data = await self.bot.api_client.get(
                self.api_endpoint,
                params=self.api_default_params
            )
        except aiohttp.ClientResponseError as e:
            self.log.exception(
                f"Failed to fetch {self.__class__.__name__} watched users from API",
                exc_info=e
            )
            return False

        self.watched_users = defaultdict(dict)

        for entry in data:
            user_id = entry.pop('user')
            self.watched_users[user_id] = entry

        return True

    async def on_message(self, msg: Message):
        """Queues up messages sent by watched users."""
        if msg.author.id in self.watched_users:
            if not self.consuming_messages:
                self._consume_task = self.bot.loop.create_task(self.consume_messages())

            self.log.trace(f"Received message: {msg.content} ({len(msg.attachments)} attachments)")
            self.message_queue[msg.author.id][msg.channel.id].append(msg)

    async def consume_messages(self, delay_consumption: bool = True):
        """Consumes the message queues to log watched users' messages."""
        if delay_consumption:
            self.log.trace(f"Sleeping {BigBrotherConfig.log_delay} seconds before consuming message queue")
            await asyncio.sleep(1)

        self.log.trace(f"{self.__class__.__name__} started consuming the message queue")

        # Prevent losing a partly processed consumption queue after Task failure
        if not self.consumption_queue:
            self.consumption_queue = self.message_queue.copy()
            self.message_queue.clear()

        for user_channel_queues in self.consumption_queue.values():
            for channel_queue in user_channel_queues.values():
                while channel_queue:
                    msg = channel_queue.popleft()

                    self.log.trace(f"Consuming message {msg.id} ({len(msg.attachments)} attachments)")
                    await self.relay_message(msg)

        self.consumption_queue.clear()

        if self.message_queue:
            self.log.trace("Channel queue not empty: Continuing consuming queues")
            self._consume_task = self.bot.loop.create_task(
                self.consume_messages(delay_consumption=False)
            )
        else:
            self.log.trace("Done consuming messages.")

    async def webhook_send(
        self, content: Optional[str] = None, username: Optional[str] = None,
        avatar_url: Optional[str] = None, embed: Optional[Embed] = None,
    ):
        """Sends a message to the webhook with the specified kwargs."""
        try:
            await self.webhook.send(content=content, username=username, avatar_url=avatar_url, embed=embed)
        except discord.HTTPException as exc:
            self.log.exception(
                f"Failed to send message to {self.__class__.__name__} webhook",
                exc_info=exc
            )

    async def relay_message(self, msg: Message) -> None:
        """Relays the message to the relevant WatchChannel"""
        last_author, last_channel, count = self.message_history
        limit = BigBrotherConfig.header_message_limit

        if msg.author.id != last_author or msg.channel.id != last_channel or count >= limit:
            self.message_history = [msg.author.id, msg.channel.id, 0]

            await self.send_header(msg)

        cleaned_content = msg.clean_content

        if cleaned_content:
            media_urls = {embed.url for embed in msg.embeds if embed.type in ("image", "video")}
            for url in URL_RE.findall(cleaned_content):
                if url not in media_urls:
                    cleaned_content = cleaned_content.replace(url, f"`{url}`")
            await self.webhook_send(
                cleaned_content,
                username=msg.author.display_name,
                avatar_url=msg.author.avatar_url
            )

        if msg.attachments:
            try:
                await messages.send_attachments(msg, self.webhook)
            except (errors.Forbidden, errors.NotFound):
                e = Embed(
                    description=":x: **This message contained an attachment, but it could not be retrieved**",
                    color=Color.red()
                )
                await self.webhook_send(
                    embed=e,
                    username=msg.author.display_name,
                    avatar_url=msg.author.avatar_url
                )
            except discord.HTTPException as exc:
                self.log.exception(
                    f"Failed to send an attachment to {self.__class__.__name__} webhook",
                    exc_info=exc
                )

        self.message_history[2] += 1

    async def send_header(self, msg):
        """Sends an header embed to the WatchChannel"""
        user_id = msg.author.id

        guild = self.bot.get_guild(GuildConfig.id)
        actor = guild.get_member(self.watched_users[user_id]['actor'])
        actor = actor.display_name if actor else self.watched_users[user_id]['actor']

        inserted_at = self.watched_users[user_id]['inserted_at']
        date_time = datetime.datetime.strptime(
            inserted_at,
            "%Y-%m-%dT%H:%M:%S.%fZ"
        ).replace(tzinfo=None)
        time_delta = time_since(date_time, precision="minutes", max_units=1)

        reason = self.watched_users[user_id]['reason']

        embed = Embed(description=(
            f"{msg.author.mention} in [#{msg.channel.name}]({msg.jump_url})\n"
        ))
        embed.set_footer(text=(
            f"Added {time_delta} by {actor} | "
            f"Reason: {reason}"
        ))
        await self.webhook_send(
            embed=embed,
            username=msg.author.display_name,
            avatar_url=msg.author.avatar_url
        )

    async def list_watched_users(self, ctx: Context, update_cache: bool = False) -> None:
        """
        Gives an overview of the watched user list for this channel.

        The optional kwarg `update_cache` specifies whether the cache should
        be refreshed by polling the API.
        """

        if update_cache:
            if not await self.fetch_user_cache():
                e = Embed(
                    description=f":x: **Failed to update {self.__class__.__name__} user cache**",
                    color=Color.red()
                )
                await ctx.send(embed=e)
                return

        lines = []
        for user_id, user_data in self.watched_users.items():
            inserted_at = user_data['inserted_at']
            time_delta = self._get_time_delta(inserted_at)
            lines.append(f"• <@{user_id}> (added {time_delta})")

        await LinePaginator.paginate(
            lines or ("There's nothing here yet.",),
            ctx,
            Embed(
                title=f"{self.__class__.__name__} watched users ({'updated' if update_cache else 'cached'})",
                color=Color.blue()
            ),
            empty=False
        )

    @staticmethod
    def _get_time_delta(time_string: str) -> str:
        """Returns the time in human-readable time delta format"""

        date_time = datetime.datetime.strptime(
            time_string,
            "%Y-%m-%dT%H:%M:%S.%fZ"
        ).replace(tzinfo=None)
        time_delta = time_since(date_time, precision="minutes", max_units=1)

        return time_delta

    @staticmethod
    def _get_human_readable(time_string: str, output_format: str = "%Y-%m-%d %H:%M:%S") -> str:
        date_time = datetime.datetime.strptime(
            time_string,
            "%Y-%m-%dT%H:%M:%S.%fZ"
        ).replace(tzinfo=None)
        return date_time.strftime(output_format)

    def _remove_user(self, user_id: int) -> None:
        """Removes user from the WatchChannel"""

        self.watched_users.pop(user_id, None)
        self.message_queue.pop(user_id, None)
        self.consumption_queue.pop(user_id, None)

    def cog_unload(self):
        """Takes care of unloading the cog and cancelling the consumption task."""

        self.log.trace(f"Unloading {self.__class__._name__} cog")
        if not self._consume_task.done():
            self._consume_task.cancel()
            try:
                self._consume_task.result()
            except asyncio.CancelledError as e:
                self.log.exception(
                    f"The {self.__class__._name__} consume task was cancelled. Messages may be lost.",
                    exc_info=e
                )
