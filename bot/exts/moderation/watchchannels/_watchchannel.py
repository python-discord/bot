import asyncio
import logging
import re
import textwrap
from abc import abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Optional

import dateutil.parser
import discord
from discord import Color, DMChannel, Embed, HTTPException, Message, errors
from discord.ext.commands import Cog, Context

from bot.api import ResponseCodeError
from bot.bot import Bot
from bot.constants import BigBrother as BigBrotherConfig, Guild as GuildConfig, Icons
from bot.exts.filters.token_remover import TokenRemover
from bot.exts.filters.webhook_remover import WEBHOOK_URL_RE
from bot.exts.moderation.modlog import ModLog
from bot.pagination import LinePaginator
from bot.utils import CogABCMeta, messages
from bot.utils.time import time_since

log = logging.getLogger(__name__)

URL_RE = re.compile(r"(https?://[^\s]+)")


@dataclass
class MessageHistory:
    """Represents a watch channel's message history."""

    last_author: Optional[int] = None
    last_channel: Optional[int] = None
    message_count: int = 0


class WatchChannel(metaclass=CogABCMeta):
    """ABC with functionality for relaying users' messages to a certain channel."""

    @abstractmethod
    def __init__(
        self,
        bot: Bot,
        destination: int,
        webhook_id: int,
        api_endpoint: str,
        api_default_params: dict,
        logger: logging.Logger
    ) -> None:
        self.bot = bot

        self.destination = destination  # E.g., Channels.big_brother_logs
        self.webhook_id = webhook_id  # E.g.,  Webhooks.big_brother
        self.api_endpoint = api_endpoint  # E.g., 'bot/infractions'
        self.api_default_params = api_default_params  # E.g., {'active': 'true', 'type': 'watch'}
        self.log = logger  # Logger of the child cog for a correct name in the logs

        self._consume_task = None
        self.watched_users = defaultdict(dict)
        self.message_queue = defaultdict(lambda: defaultdict(deque))
        self.consumption_queue = {}
        self.retries = 5
        self.retry_delay = 10
        self.channel = None
        self.webhook = None
        self.message_history = MessageHistory()

        self._start = self.bot.loop.create_task(self.start_watchchannel())

    @property
    def modlog(self) -> ModLog:
        """Provides access to the ModLog cog for alert purposes."""
        return self.bot.get_cog("ModLog")

    @property
    def consuming_messages(self) -> bool:
        """Checks if a consumption task is currently running."""
        if self._consume_task is None:
            return False

        if self._consume_task.done():
            exc = self._consume_task.exception()
            if exc:
                self.log.exception(
                    "The message queue consume task has failed with:",
                    exc_info=exc
                )
            return False

        return True

    async def start_watchchannel(self) -> None:
        """Starts the watch channel by getting the channel, webhook, and user cache ready."""
        await self.bot.wait_until_guild_available()

        try:
            self.channel = await self.bot.fetch_channel(self.destination)
        except HTTPException:
            self.log.exception(f"Failed to retrieve the text channel with id `{self.destination}`")

        try:
            self.webhook = await self.bot.fetch_webhook(self.webhook_id)
        except discord.HTTPException:
            self.log.exception(f"Failed to fetch webhook with id `{self.webhook_id}`")

        if self.channel is None or self.webhook is None:
            self.log.error("Failed to start the watch channel; unloading the cog.")

            message = textwrap.dedent(
                f"""
                An error occurred while loading the text channel or webhook.

                TextChannel: {"**Failed to load**" if self.channel is None else "Loaded successfully"}
                Webhook: {"**Failed to load**" if self.webhook is None else "Loaded successfully"}

                The Cog has been unloaded.
                """
            )

            await self.modlog.send_log_message(
                title=f"Error: Failed to initialize the {self.__class__.__name__} watch channel",
                text=message,
                ping_everyone=True,
                icon_url=Icons.token_removed,
                colour=Color.red()
            )

            self.bot.remove_cog(self.__class__.__name__)
            return

        if not await self.fetch_user_cache():
            await self.modlog.send_log_message(
                title=f"Warning: Failed to retrieve user cache for the {self.__class__.__name__} watch channel",
                text="Could not retrieve the list of watched users from the API and messages will not be relayed.",
                ping_everyone=True,
                icon_url=Icons.token_removed,
                colour=Color.red()
            )

    async def fetch_user_cache(self) -> bool:
        """
        Fetches watched users from the API and updates the watched user cache accordingly.

        This function returns `True` if the update succeeded.
        """
        try:
            data = await self.bot.api_client.get(self.api_endpoint, params=self.api_default_params)
        except ResponseCodeError as err:
            self.log.exception("Failed to fetch the watched users from the API", exc_info=err)
            return False

        self.watched_users = defaultdict(dict)

        for entry in data:
            user_id = entry.pop('user')
            self.watched_users[user_id] = entry

        return True

    @Cog.listener()
    async def on_message(self, msg: Message) -> None:
        """Queues up messages sent by watched users."""
        if msg.author.id in self.watched_users:
            if not self.consuming_messages:
                self._consume_task = self.bot.loop.create_task(self.consume_messages())

            self.log.trace(f"Received message: {msg.content} ({len(msg.attachments)} attachments)")
            self.message_queue[msg.author.id][msg.channel.id].append(msg)

    async def consume_messages(self, delay_consumption: bool = True) -> None:
        """Consumes the message queues to log watched users' messages."""
        if delay_consumption:
            self.log.trace(f"Sleeping {BigBrotherConfig.log_delay} seconds before consuming message queue")
            await asyncio.sleep(BigBrotherConfig.log_delay)

        self.log.trace("Started consuming the message queue")

        # If the previous consumption Task failed, first consume the existing comsumption_queue
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
            self._consume_task = self.bot.loop.create_task(self.consume_messages(delay_consumption=False))
        else:
            self.log.trace("Done consuming messages.")

    async def webhook_send(
        self,
        content: Optional[str] = None,
        username: Optional[str] = None,
        avatar_url: Optional[str] = None,
        embed: Optional[Embed] = None,
    ) -> None:
        """Sends a message to the webhook with the specified kwargs."""
        username = messages.sub_clyde(username)
        try:
            await self.webhook.send(content=content, username=username, avatar_url=avatar_url, embed=embed)
        except discord.HTTPException as exc:
            self.log.exception(
                "Failed to send a message to the webhook",
                exc_info=exc
            )

    async def relay_message(self, msg: Message) -> None:
        """Relays the message to the relevant watch channel."""
        limit = BigBrotherConfig.header_message_limit

        if (
            msg.author.id != self.message_history.last_author
            or msg.channel.id != self.message_history.last_channel
            or self.message_history.message_count >= limit
        ):
            self.message_history = MessageHistory(last_author=msg.author.id, last_channel=msg.channel.id)

            await self.send_header(msg)

        if TokenRemover.find_token_in_message(msg) or WEBHOOK_URL_RE.search(msg.content):
            cleaned_content = "Content is censored because it contains a bot or webhook token."
        elif cleaned_content := msg.clean_content:
            # Put all non-media URLs in a code block to prevent embeds
            media_urls = {embed.url for embed in msg.embeds if embed.type in ("image", "video")}
            for url in URL_RE.findall(cleaned_content):
                if url not in media_urls:
                    cleaned_content = cleaned_content.replace(url, f"`{url}`")

        if cleaned_content:
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
                    "Failed to send an attachment to the webhook",
                    exc_info=exc
                )

        self.message_history.message_count += 1

    async def send_header(self, msg: Message) -> None:
        """Sends a header embed with information about the relayed messages to the watch channel."""
        user_id = msg.author.id

        guild = self.bot.get_guild(GuildConfig.id)
        actor = guild.get_member(self.watched_users[user_id]['actor'])
        actor = actor.display_name if actor else self.watched_users[user_id]['actor']

        inserted_at = self.watched_users[user_id]['inserted_at']
        time_delta = self._get_time_delta(inserted_at)

        reason = self.watched_users[user_id]['reason']

        if isinstance(msg.channel, DMChannel):
            # If a watched user DMs the bot there won't be a channel name or jump URL
            # This could technically include a GroupChannel but bot's can't be in those
            message_jump = "via DM"
        else:
            message_jump = f"in [#{msg.channel.name}]({msg.jump_url})"

        footer = f"Added {time_delta} by {actor} | Reason: {reason}"
        embed = Embed(description=f"{msg.author.mention} {message_jump}")
        embed.set_footer(text=textwrap.shorten(footer, width=128, placeholder="..."))

        await self.webhook_send(embed=embed, username=msg.author.display_name, avatar_url=msg.author.avatar_url)

    async def list_watched_users(
        self, ctx: Context, oldest_first: bool = False, update_cache: bool = True
    ) -> None:
        """
        Gives an overview of the watched user list for this channel.

        The optional kwarg `oldest_first` orders the list by oldest entry.

        The optional kwarg `update_cache` specifies whether the cache should
        be refreshed by polling the API.
        """
        if update_cache:
            if not await self.fetch_user_cache():
                await ctx.send(f":x: Failed to update {self.__class__.__name__} user cache, serving from cache")
                update_cache = False

        lines = []
        for user_id, user_data in self.watched_users.items():
            inserted_at = user_data['inserted_at']
            time_delta = self._get_time_delta(inserted_at)
            lines.append(f"• <@{user_id}> (added {time_delta})")

        if oldest_first:
            lines.reverse()

        lines = lines or ("There's nothing here yet.",)

        embed = Embed(
            title=f"{self.__class__.__name__} watched users ({'updated' if update_cache else 'cached'})",
            color=Color.blue()
        )
        await LinePaginator.paginate(lines, ctx, embed, empty=False)

    @staticmethod
    def _get_time_delta(time_string: str) -> str:
        """Returns the time in human-readable time delta format."""
        date_time = dateutil.parser.isoparse(time_string).replace(tzinfo=None)
        time_delta = time_since(date_time, precision="minutes", max_units=1)

        return time_delta

    def _remove_user(self, user_id: int) -> None:
        """Removes a user from a watch channel."""
        self.watched_users.pop(user_id, None)
        self.message_queue.pop(user_id, None)
        self.consumption_queue.pop(user_id, None)

    def cog_unload(self) -> None:
        """Takes care of unloading the cog and canceling the consumption task."""
        self.log.trace("Unloading the cog")
        if self._consume_task and not self._consume_task.done():
            def done_callback(task: asyncio.Task) -> None:
                """Send exception when consuming task have been cancelled."""
                try:
                    task.result()
                except asyncio.CancelledError:
                    self.log.info(
                        f"The consume task of {type(self).__name__} was canceled. Messages may be lost."
                    )

            self._consume_task.add_done_callback(done_callback)
            self._consume_task.cancel()
