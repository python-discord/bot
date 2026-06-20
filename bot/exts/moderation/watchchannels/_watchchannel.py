import asyncio
import re
import textwrap
from abc import abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

import discord
from discord import Color, DMChannel, Embed, HTTPException, Message, errors
from discord.ext.commands import Cog, Context
from pydis_core.site_api import ResponseCodeError
from pydis_core.utils import scheduling
from pydis_core.utils.channel import get_or_fetch_channel
from pydis_core.utils.logging import CustomLogger
from pydis_core.utils.members import get_or_fetch_member

from bot.bot import Bot
from bot.constants import BigBrother as BigBrotherConfig, Guild as GuildConfig, Icons
from bot.exts.filtering._filters.unique.discord_token import DiscordTokenFilter
from bot.exts.filtering._filters.unique.webhook import WEBHOOK_URL_RE
from bot.log import get_logger
from bot.pagination import LinePaginator
from bot.utils import CogABCMeta, messages, time
from bot.utils.modlog import send_log_message

log = get_logger(__name__)

URL_RE = re.compile(r"(https?://[^\s]+)")


@dataclass
class MessageHistory:
    """Represents a watch channel's message history."""

    last_author: int | None = None
    last_channel: int | None = None
    message_count: int = 0


@dataclass
class WatchChannelConfig:
    """Configuration for a watch channel."""

    bot: Bot
    destination: int
    webhook_id: int
    api_endpoint: str
    api_default_params: dict
    logger: CustomLogger
    disable_header: bool = False


@dataclass
class MessageQueueState:
    """State for the message consumption queue."""

    consume_task: asyncio.Task | None = None
    message_queue: defaultdict | None = None
    consumption_queue: dict | None = None
    message_history: MessageHistory | None = None

    def __post_init__(self) -> None:
        if self.message_queue is None:
            self.message_queue = defaultdict(lambda: defaultdict(deque))
        if self.consumption_queue is None:
            self.consumption_queue = {}
        if self.message_history is None:
            self.message_history = MessageHistory()


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
        logger: CustomLogger,
        *,
        disable_header: bool = False
    ) -> None:
        self.config = WatchChannelConfig(
            bot=bot,
            destination=destination,
            webhook_id=webhook_id,
            api_endpoint=api_endpoint,
            api_default_params=api_default_params,
            logger=logger,
            disable_header=disable_header,
        )
        self.queue_state = MessageQueueState()
        self.watched_users = {}
        self.channel = None
        self.webhook = None

    @property
    def bot(self) -> Bot:
        """Return the bot instance from config."""
        return self.config.bot

    @property
    def log(self) -> CustomLogger:
        """Return the logger from config."""
        return self.config.logger

    @property
    def consuming_messages(self) -> bool:
        """Checks if a consumption task is currently running."""
        if self.queue_state.consume_task is None:
            return False

        if self.queue_state.consume_task.done():
            exc = self.queue_state.consume_task.exception()
            if exc:
                self.log.exception(
                    "The message queue consume task has failed with:",
                    exc_info=exc
                )
            return False

        return True

    async def cog_load(self) -> None:
        """Starts the watch channel by getting the channel, webhook, and user cache ready."""
        await self.bot.wait_until_guild_available()

        try:
            self.channel = await get_or_fetch_channel(self.bot, self.config.destination)
        except HTTPException:
            self.log.exception(f"Failed to retrieve the text channel with id `{self.config.destination}`")

        try:
            self.webhook = await self.bot.fetch_webhook(self.config.webhook_id)
        except discord.HTTPException:
            self.log.exception(f"Failed to fetch webhook with id `{self.config.webhook_id}`")

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

            await send_log_message(
                self.bot,
                title=f"Error: Failed to initialize the {self.__class__.__name__} watch channel",
                text=message,
                ping_everyone=True,
                icon_url=Icons.token_removed,
                colour=Color.red()
            )

            await self.bot.remove_cog(self.__class__.__name__)
            return

        if not await self.fetch_user_cache():
            await send_log_message(
                self.bot,
                title=f"Warning: Failed to retrieve user cache for the {self.__class__.__name__} watch channel",
                text=(
                    "Could not retrieve the list of watched users from the API. "
                    "Messages will not be relayed, and reviews not rescheduled."
                ),
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
            data = await self.bot.api_client.get(self.config.api_endpoint, params=self.config.api_default_params)
        except ResponseCodeError as err:
            self.log.exception("Failed to fetch the watched users from the API", exc_info=err)
            return False

        self.watched_users.clear()

        for entry in data:
            user_id = entry.pop("user")
            self.watched_users[user_id] = entry

        return True

    @Cog.listener()
    async def on_message(self, msg: Message) -> None:
        """Queues up messages sent by watched users."""
        if msg.author.id in self.watched_users:
            if not self.consuming_messages:
                self.queue_state.consume_task = scheduling.create_task(self.consume_messages())

            self.log.trace(f"Received message: {msg.content} ({len(msg.attachments)} attachments)")
            self.queue_state.message_queue[msg.author.id][msg.channel.id].append(msg)

    async def consume_messages(self, delay_consumption: bool = True) -> None:
        """Consumes the message queues to log watched users' messages."""
        if delay_consumption:
            self.log.trace(f"Sleeping {BigBrotherConfig.log_delay} seconds before consuming message queue")
            await asyncio.sleep(BigBrotherConfig.log_delay)

        self.log.trace("Started consuming the message queue")

        # If the previous consumption Task failed, first consume the existing comsumption_queue
        if not self.queue_state.consumption_queue:
            self.queue_state.consumption_queue = self.queue_state.message_queue.copy()
            self.queue_state.message_queue.clear()

        for user_id, channel_queues in self.queue_state.consumption_queue.items():
            for channel_queue in channel_queues.values():
                while channel_queue:
                    msg = channel_queue.popleft()

                    if watch_info := self.watched_users.get(user_id, None):
                        self.log.trace(f"Consuming message {msg.id} ({len(msg.attachments)} attachments)")
                        await self.relay_message(msg, watch_info)
                    else:
                        self.log.trace(f"Not consuming message {msg.id} as user {user_id} is no longer watched.")

        self.queue_state.consumption_queue.clear()

        if self.queue_state.message_queue:
            self.log.trace("Channel queue not empty: Continuing consuming queues")
            self.queue_state.consume_task = scheduling.create_task(self.consume_messages(delay_consumption=False))
        else:
            self.log.trace("Done consuming messages.")

    async def webhook_send(
        self,
        content: str | None = None,
        username: str | None = None,
        avatar_url: str | None = None,
        embed: Embed | None = None,
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

    async def relay_message(self, msg: Message, watch_info: dict) -> None:
        """Relays the message to the relevant watch channel."""
        limit = BigBrotherConfig.header_message_limit

        if (
            msg.author.id != self.queue_state.message_history.last_author
            or msg.channel.id != self.queue_state.message_history.last_channel
            or self.queue_state.message_history.message_count >= limit
        ):
            self.queue_state.message_history = MessageHistory(last_author=msg.author.id, last_channel=msg.channel.id)

            await self.send_header(msg, watch_info)

        if DiscordTokenFilter.find_token_in_message(msg.content) or WEBHOOK_URL_RE.search(msg.content):
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
                avatar_url=msg.author.display_avatar.url
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
                    avatar_url=msg.author.display_avatar.url
                )
            except discord.HTTPException as exc:
                self.log.exception(
                    "Failed to send an attachment to the webhook",
                    exc_info=exc
                )

        self.queue_state.message_history.message_count += 1

    async def send_header(self, msg: Message, watch_info: dict) -> None:
        """Sends a header embed with information about the relayed messages to the watch channel."""
        if self.config.disable_header:
            return

        guild = self.bot.get_guild(GuildConfig.id)
        actor = await get_or_fetch_member(guild, watch_info["actor"])
        actor = actor.display_name if actor else watch_info["actor"]

        inserted_at = watch_info["inserted_at"]
        time_delta = time.format_relative(inserted_at)

        reason = watch_info["reason"]

        if isinstance(msg.channel, DMChannel):
            # If a watched user DMs the bot there won't be a channel name or jump URL
            # This could technically include a GroupChannel but bot's can't be in those
            message_jump = "via DM"
        else:
            message_jump = f"in [#{msg.channel.name}]({msg.jump_url})"

        footer = f"Added {time_delta} by {actor} | Reason: {reason}"
        embed = Embed(description=f"{msg.author.mention} {message_jump}\n\n{footer}")

        await self.webhook_send(embed=embed, username=msg.author.display_name, avatar_url=msg.author.display_avatar.url)

    async def list_watched_users(
        self, ctx: Context, oldest_first: bool = False, update_cache: bool = True
    ) -> None:
        """
        Gives an overview of the watched user list for this channel.

        The optional kwarg `oldest_first` orders the list by oldest entry.

        The optional kwarg `update_cache` specifies whether the cache should
        be refreshed by polling the API.
        """
        watched_data = await self.prepare_watched_users_data(ctx, oldest_first, update_cache)

        if update_cache and not watched_data["updated"]:
            await ctx.send(f":x: Failed to update {self.__class__.__name__} user cache, serving from cache")

        lines = watched_data["info"].values() or ("There's nothing here yet.",)

        embed = Embed(
            title=watched_data["title"],
            color=Color.blue()
        )
        await LinePaginator.paginate(lines, ctx, embed, empty=False)

    async def prepare_watched_users_data(
        self, ctx: Context, oldest_first: bool = False, update_cache: bool = True
    ) -> dict[str, Any]:
        """
        Prepare overview information of watched users to list.

        The optional kwarg `oldest_first` orders the list by oldest entry.

        The optional kwarg `update_cache` specifies whether the cache should
        be refreshed by polling the API.

        Returns a dictionary with a "title" key for the list's title, and a "info" key with
        information about each user.

        The dictionary additionally has an "updated" field which is true if a cache update was
        requested and it succeeded.
        """
        list_data = {}
        if update_cache:
            if not await self.fetch_user_cache():
                update_cache = False
        list_data["updated"] = update_cache

        # Copy into list to prevent issues if it is modified elsewhere while it's being iterated over.
        watched_list = list(self.watched_users.items())
        if oldest_first:
            watched_list.reverse()

        list_data["info"] = {}
        for user_id, user_data in watched_list:
            member = await get_or_fetch_member(ctx.guild, user_id)
            line = f"- `{user_id}`"
            if member:
                line += f" ({member.name}#{member.discriminator})"
            inserted_at = user_data["inserted_at"]
            line += f", added {time.format_relative(inserted_at)}"
            if not member:  # Cross off users who left the server.
                line = f"~~{line}~~"
            list_data["info"][user_id] = line

        list_data["title"] = f"{self.__class__.__name__} watched users ({'updated' if update_cache else 'cached'})"

        return list_data

    def _remove_user(self, user_id: int) -> None:
        """Removes a user from a watch channel."""
        self.watched_users.pop(user_id, None)

    async def cog_unload(self) -> None:
        """Takes care of unloading the cog and canceling the consumption task."""
        self.log.trace("Unloading the cog")
        if self.queue_state.consume_task and not self.queue_state.consume_task.done():
            def done_callback(task: asyncio.Task) -> None:
                """Send exception when consuming task have been cancelled."""
                try:
                    task.result()
                except asyncio.CancelledError:
                    self.log.info(
                        f"The consume task of {type(self).__name__} was canceled. Messages may be lost."
                    )

            self.queue_state.consume_task.add_done_callback(done_callback)
            self.queue_state.consume_task.cancel()
