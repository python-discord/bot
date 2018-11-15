import asyncio
import logging
import re
from collections import defaultdict, deque
from typing import List, Union

from discord import Color, Embed, Guild, Member, Message, TextChannel, User
from discord.ext.commands import Bot, Context, group

from bot.constants import BigBrother as BigBrotherConfig, Channels, Emojis, Guild as GuildConfig, Keys, Roles, URLs
from bot.decorators import with_role
from bot.pagination import LinePaginator
from bot.utils import messages

log = logging.getLogger(__name__)

URL_RE = re.compile(r"(https?://[^\s]+)")


class BigBrother:
    """User monitoring to assist with moderation."""

    HEADERS = {'X-API-Key': Keys.site_api}

    def __init__(self, bot: Bot):
        self.bot = bot
        self.watched_users = {}  # { user_id: log_channel_id }
        self.channel_queues = defaultdict(lambda: defaultdict(deque))  # { user_id: { channel_id: queue(messages) }
        self.consuming = False

        self.bot.loop.create_task(self.get_watched_users())

    def update_cache(self, api_response: List[dict]):
        """
        Updates the internal cache of watched users from the given `api_response`.
        This function will only add (or update) existing keys, it will not delete
        keys that were not present in the API response.
        A user is only added if the bot can find a channel
        with the given `channel_id` in its channel cache.
        """

        for entry in api_response:
            user_id = int(entry['user_id'])
            channel_id = int(entry['channel_id'])
            channel = self.bot.get_channel(channel_id)

            if channel is not None:
                self.watched_users[user_id] = channel
            else:
                log.error(
                    f"Site specified to relay messages by `{user_id}` in `{channel_id}`, "
                    "but the given channel could not be found. Ignoring."
                )

    async def get_watched_users(self):
        """Retrieves watched users from the API."""

        await self.bot.wait_until_ready()
        async with self.bot.http_session.get(URLs.site_bigbrother_api, headers=self.HEADERS) as response:
            data = await response.json()
            self.update_cache(data)

    async def on_member_ban(self, guild: Guild, user: Union[User, Member]):
        if guild.id == GuildConfig.id and user.id in self.watched_users:
            url = f"{URLs.site_bigbrother_api}?user_id={user.id}"
            channel = self.watched_users[user.id]

            async with self.bot.http_session.delete(url, headers=self.HEADERS) as response:
                del self.watched_users[user.id]
                del self.channel_queues[user.id]
                if response.status == 204:
                    await channel.send(
                        f"{Emojis.bb_message}:hammer: {user} got banned, so "
                        f"`BigBrother` will no longer relay their messages to {channel}"
                    )

                else:
                    data = await response.json()
                    reason = data.get('error_message', "no message provided")
                    await channel.send(
                        f"{Emojis.bb_message}:x: {user} got banned, but trying to remove them from"
                        f"BigBrother's user dictionary on the API returned an error: {reason}"
                    )

    async def on_message(self, msg: Message):
        """Queues up messages sent by watched users."""

        if msg.author.id in self.watched_users:
            if not self.consuming:
                self.bot.loop.create_task(self.consume_messages())

            log.trace(f"Received message: {msg.content} ({len(msg.attachments)} attachments)")
            self.channel_queues[msg.author.id][msg.channel.id].append(msg)

    async def consume_messages(self):
        """Consumes the message queues to log watched users' messages."""

        if not self.consuming:
            self.consuming = True
            log.trace("Sleeping before consuming...")
            await asyncio.sleep(BigBrotherConfig.log_delay)

        log.trace("Begin consuming messages.")
        channel_queues = self.channel_queues.copy()
        self.channel_queues.clear()
        for user_id, queues in channel_queues.items():
            for _, queue in queues.items():
                channel = self.watched_users[user_id]

                if queue:
                    # Send a header embed before sending all messages in the queue.
                    msg = queue[0]
                    embed = Embed(description=f"{msg.author.mention} in [#{msg.channel.name}]({msg.jump_url})")
                    embed.set_author(name=msg.author.nick or msg.author.name, icon_url=msg.author.avatar_url)
                    await channel.send(embed=embed)

                while queue:
                    msg = queue.popleft()
                    log.trace(f"Consuming message: {msg.clean_content} ({len(msg.attachments)} attachments)")
                    await self.log_message(msg, channel)

        if self.channel_queues:
            log.trace("Queue not empty; continue consumption.")
            self.bot.loop.create_task(self.consume_messages())
        else:
            log.trace("Done consuming messages.")
            self.consuming = False

    @staticmethod
    async def log_message(message: Message, destination: TextChannel):
        """
        Logs a watched user's message in the given channel.

        Attachments are also sent. All non-image or non-video URLs are put in inline code blocks to prevent preview
        embeds from being automatically generated.

        :param message: the message to log
        :param destination: the channel in which to log the message
        """

        content = message.clean_content
        if content:
            # Put all non-media URLs in inline code blocks.
            media_urls = {embed.url for embed in message.embeds if embed.type in ("image", "video")}
            for url in URL_RE.findall(content):
                if url not in media_urls:
                    content = content.replace(url, f"`{url}`")

            await destination.send(content)

        await messages.send_attachments(message, destination)

    @group(name='bigbrother', aliases=('bb',), invoke_without_command=True)
    @with_role(Roles.owner, Roles.admin, Roles.moderator)
    async def bigbrother_group(self, ctx: Context):
        """Monitor users, NSA-style."""

        await ctx.invoke(self.bot.get_command("help"), "bigbrother")

    @bigbrother_group.command(name='watched', aliases=('all',))
    @with_role(Roles.owner, Roles.admin, Roles.moderator)
    async def watched_command(self, ctx: Context, from_cache: bool = True):
        """
        Shows all users that are currently monitored and in which channel.
        By default, the users are returned from the cache.
        If this is not desired, `from_cache` can be given as a falsy value, e.g. e.g. 'no'.
        """

        if from_cache:
            lines = tuple(
                f"• <@{user_id}> in <#{self.watched_users[user_id].id}>"
                for user_id in self.watched_users
            )
            await LinePaginator.paginate(
                lines or ("There's nothing here yet.",),
                ctx,
                Embed(title="Watched users (cached)", color=Color.blue()),
                empty=False
            )

        else:
            async with self.bot.http_session.get(URLs.site_bigbrother_api, headers=self.HEADERS) as response:
                if response.status == 200:
                    data = await response.json()
                    self.update_cache(data)
                    lines = tuple(f"• <@{entry['user_id']}> in <#{entry['channel_id']}>" for entry in data)

                    await LinePaginator.paginate(
                        lines or ("There's nothing here yet.",),
                        ctx,
                        Embed(title="Watched users", color=Color.blue()),
                        empty=False
                    )

                else:
                    await ctx.send(f":x: got non-200 response from the API")

    @bigbrother_group.command(name='watch', aliases=('w',))
    @with_role(Roles.owner, Roles.admin, Roles.moderator)
    async def watch_command(self, ctx: Context, user: User, channel: TextChannel = None):
        """
        Relay messages sent by the given `user` in the given `channel`.
        If `channel` is not specified, logs to the mod log channel.
        """

        if channel is not None:
            channel_id = channel.id
        else:
            channel_id = Channels.big_brother_logs

        post_data = {
            'user_id': str(user.id),
            'channel_id': str(channel_id)
        }

        async with self.bot.http_session.post(
            URLs.site_bigbrother_api,
            headers=self.HEADERS,
            json=post_data
        ) as response:
            if response.status == 204:
                await ctx.send(f":ok_hand: will now relay messages sent by {user} in <#{channel_id}>")

                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    log.error(
                        f"could not update internal cache, failed to find a channel with ID {channel_id}"
                    )
                else:
                    self.watched_users[user.id] = channel

            else:
                data = await response.json()
                reason = data.get('error_message', "no message provided")
                await ctx.send(f":x: the API returned an error: {reason}")

    @bigbrother_group.command(name='unwatch', aliases=('uw',))
    @with_role(Roles.owner, Roles.admin, Roles.moderator)
    async def unwatch_command(self, ctx: Context, user: User):
        """Stop relaying messages by the given `user`."""

        url = f"{URLs.site_bigbrother_api}?user_id={user.id}"
        async with self.bot.http_session.delete(url, headers=self.HEADERS) as response:
            if response.status == 204:
                await ctx.send(f":ok_hand: will no longer relay messages sent by {user}")

                if user.id in self.watched_users:
                    del self.watched_users[user.id]
                    if user.id in self.channel_queues:
                        del self.channel_queues[user.id]
                else:
                    log.warning(f"user {user.id} was unwatched but was not found in the cache")

            else:
                data = await response.json()
                reason = data.get('error_message', "no message provided")
                await ctx.send(f":x: the API returned an error: {reason}")


def setup(bot: Bot):
    bot.add_cog(BigBrother(bot))
    log.info("Cog loaded: BigBrother")
