import asyncio
import logging
import re
from collections import defaultdict, deque
from time import strptime, struct_time
from typing import List, NamedTuple, Optional, Union

from aiohttp import ClientError
from discord import Color, Embed, Guild, Member, Message, TextChannel, User
from discord.ext.commands import Bot, Context, command, group

from bot.constants import BigBrother as BigBrotherConfig, Channels, Emojis, Guild as GuildConfig, Keys, Roles, URLs
from bot.decorators import with_role
from bot.pagination import LinePaginator
from bot.utils import messages
from bot.utils.moderation import post_infraction
from bot.utils.time import parse_rfc1123, time_since

log = logging.getLogger(__name__)

URL_RE = re.compile(r"(https?://[^\s]+)")


class WatchInformation(NamedTuple):
    reason: str
    actor_id: Optional[int]
    inserted_at: Optional[str]


class BigBrother:
    """User monitoring to assist with moderation."""

    HEADERS = {'X-API-Key': Keys.site_api}

    def __init__(self, bot: Bot):
        self.bot = bot
        self.watched_users = {}  # { user_id: log_channel_id }
        self.watch_reasons = {}  # { user_id: watch_reason }
        self.channel_queues = defaultdict(lambda: defaultdict(deque))  # { user_id: { channel_id: queue(messages) }
        self.last_log = [None, None, 0]  # [user_id, channel_id, message_count]
        self.consuming = False
        self.infraction_watch_prefix = "bb watch: "  # Please do not change or we won't be able to find old reasons

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

    async def get_watch_information(self, user_id: int) -> WatchInformation:
        """ Fetches and returns the latest watch reason for a user using the infraction API """

        re_bb_watch = rf"^{self.infraction_watch_prefix}"
        user_id = str(user_id)

        try:
            response = await self.bot.http_session.get(
                URLs.site_infractions_user_type.format(
                    user_id=user_id,
                    infraction_type="note",
                ),
                params={"search": re_bb_watch, "hidden": "True", "active": "False"},
                headers=self.HEADERS
            )
            infraction_list = await response.json()
        except ClientError:
            log.exception(f"Failed to retrieve bb watch reason for {user_id}.")
            return WatchInformation(reason="(error retrieving bb reason)", actor_id=None, inserted_at=None)

        if infraction_list:
            # Get the latest watch reason
            latest_reason_infraction = max(infraction_list, key=self._parse_infraction_time)

            # Get the actor of the watch/nominate action
            actor_id = int(latest_reason_infraction["actor"]["user_id"])

            # Get the date the watch was set
            date = latest_reason_infraction["inserted_at"]

            # Get the latest reason without the prefix
            latest_reason = latest_reason_infraction['reason'][len(self.infraction_watch_prefix):]

            log.trace(f"The latest bb watch reason for {user_id}: {latest_reason}")
            return WatchInformation(reason=latest_reason, actor_id=actor_id, inserted_at=date)

        log.trace(f"No bb watch reason found for {user_id}; returning defaults")
        return WatchInformation(reason="(no reason specified)", actor_id=None, inserted_at=None)

    @staticmethod
    def _parse_infraction_time(infraction: dict) -> struct_time:
        """
        Helper function that retrieves the insertion time from the infraction dictionary,
        converts the retrieved RFC1123 date_time string to a time object, and returns it
        so infractions can be sorted by their insertion time.
        """

        date_string = infraction["inserted_at"]
        return strptime(date_string, "%a, %d %b %Y %H:%M:%S %Z")

    async def on_member_ban(self, guild: Guild, user: Union[User, Member]):
        if guild.id == GuildConfig.id and user.id in self.watched_users:
            url = f"{URLs.site_bigbrother_api}?user_id={user.id}"
            channel = self.watched_users[user.id]

            async with self.bot.http_session.delete(url, headers=self.HEADERS) as response:
                del self.watched_users[user.id]
                del self.channel_queues[user.id]
                del self.watch_reasons[user.id]
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
                while queue:
                    msg = queue.popleft()
                    log.trace(f"Consuming message: {msg.clean_content} ({len(msg.attachments)} attachments)")

                    self.last_log[2] += 1  # Increment message count.
                    await self.send_header(msg, channel)
                    await self.log_message(msg, channel)

        if self.channel_queues:
            log.trace("Queue not empty; continue consumption.")
            self.bot.loop.create_task(self.consume_messages())
        else:
            log.trace("Done consuming messages.")
            self.consuming = False

    async def send_header(self, message: Message, destination: TextChannel):
        """
        Sends a log message header to the given channel.

        A header is only sent if the user or channel are different than the previous, or if the configured message
        limit for a single header has been exceeded.

        :param message: the first message in the queue
        :param destination: the channel in which to send the header
        """

        last_user, last_channel, msg_count = self.last_log
        limit = BigBrotherConfig.header_message_limit

        # Send header if user/channel are different or if message limit exceeded.
        if message.author.id != last_user or message.channel.id != last_channel or msg_count > limit:
            # Retrieve watch reason from API if it's not already in the cache
            if message.author.id not in self.watch_reasons:
                log.trace(f"No watch information for {message.author.id} found in cache; retrieving from API")
                user_watch_information = await self.get_watch_information(message.author.id)
                self.watch_reasons[message.author.id] = user_watch_information

            self.last_log = [message.author.id, message.channel.id, 0]

            # Get reason, actor, inserted_at
            reason, actor_id, inserted_at = self.watch_reasons[message.author.id]

            # Setting up the default author_field
            author_field = message.author.nick or message.author.name

            # When we're dealing with a talent-pool header, add nomination info to the author field
            if destination == self.bot.get_channel(Channels.talent_pool):
                log.trace("We're sending a header to the talent-pool; let's add nomination info")
                # If a reason was provided, both should be known
                if actor_id and inserted_at:
                    # Parse actor name
                    guild: GuildConfig = self.bot.get_guild(GuildConfig.id)
                    actor_as_member = guild.get_member(actor_id)
                    actor = actor_as_member.nick or actor_as_member.name

                    # Get time delta since insertion
                    date_time = parse_rfc1123(inserted_at).replace(tzinfo=None)
                    time_delta = time_since(date_time, precision="minutes", max_units=1)

                    # Adding nomination info to author_field
                    author_field = f"{author_field} (nominated {time_delta} by {actor})"

            embed = Embed(description=f"{message.author.mention} in [#{message.channel.name}]({message.jump_url})")
            embed.set_author(name=author_field, icon_url=message.author.avatar_url)
            embed.set_footer(text=f"Reason: {reason}")
            await destination.send(embed=embed)

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

    async def _watch_user(self, ctx: Context, user: User, reason: str, channel_id: int):
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
                if channel_id == Channels.talent_pool:
                    await ctx.send(f":ok_hand: added {user} to the <#{channel_id}>!")
                else:
                    await ctx.send(f":ok_hand: will now relay messages sent by {user} in <#{channel_id}>")

                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    log.error(
                        f"could not update internal cache, failed to find a channel with ID {channel_id}"
                    )
                else:
                    self.watched_users[user.id] = channel

                    # Add a note (shadow warning) with the reason for watching
                    reason = f"{self.infraction_watch_prefix}{reason}"
                    await post_infraction(ctx, user, type="warning", reason=reason, hidden=True)
            else:
                data = await response.json()
                error_reason = data.get('error_message', "no message provided")
                await ctx.send(f":x: the API returned an error: {error_reason}")

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
    async def watch_command(self, ctx: Context, user: User, *, reason: str):
        """
        Relay messages sent by the given `user` to the `#big-brother-logs` channel

        A `reason` for watching is required, which is added for the user to be watched as a
        note (aka: shadow warning)
        """

        channel_id = Channels.big_brother_logs

        await self._watch_user(ctx, user, reason, channel_id)

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
                    if user.id in self.watch_reasons:
                        del self.watch_reasons[user.id]
                else:
                    log.warning(f"user {user.id} was unwatched but was not found in the cache")

            else:
                data = await response.json()
                reason = data.get('error_message', "no message provided")
                await ctx.send(f":x: the API returned an error: {reason}")

    @bigbrother_group.command(name='nominate', aliases=('n',))
    @with_role(Roles.owner, Roles.admin, Roles.moderator)
    async def nominate_command(self, ctx: Context, user: User, *, reason: str):
        """
        Nominates a user for the helper role by adding them to the talent-pool channel

        A `reason` for the nomination is required and will be added as a note to
        the user's records.
        """

        # Note: This function is called from HelperNomination.nominate_command so that the
        # !nominate command does not show up under "BigBrother" in the help embed, but under
        # the header HelperNomination for users with the helper role.

        channel_id = Channels.talent_pool

        await self._watch_user(ctx, user, reason, channel_id)


class HelperNomination:
    def __init__(self, bot):
        self.bot = bot

    @command(name='nominate', aliases=('n',))
    @with_role(Roles.owner, Roles.admin, Roles.moderator, Roles.helpers)
    async def nominate_command(self, ctx: Context, user: User, *, reason: str):
        """
        Nominates a user for the helper role by adding them to the talent-pool channel

        A `reason` for the nomination is required and will be added as a note to
        the user's records.
        """

        cmd = self.bot.get_command("bigbrother nominate")

        await ctx.invoke(cmd, user, reason=reason)


def setup(bot: Bot):
    bot.add_cog(BigBrother(bot))
    bot.add_cog(HelperNomination(bot))
    log.info("Cog loaded: BigBrother")
