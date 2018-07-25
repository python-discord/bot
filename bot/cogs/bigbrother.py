import logging
from typing import List, Union

from discord import Color, Embed, Guild, Member, Message, TextChannel, User
from discord.ext.commands import Bot, Context, command

from bot.constants import Channels, Emojis, Guild as GuildConfig, Keys, Roles, URLs
from bot.decorators import with_role
from bot.pagination import LinePaginator


log = logging.getLogger(__name__)


class BigBrother:
    """User monitoring to assist with moderation."""

    HEADERS = {'X-API-Key': Keys.site_api}

    def __init__(self, bot: Bot):
        self.bot = bot
        self.watched_users = {}

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

    async def on_ready(self):
        async with self.bot.http_session.get(URLs.site_bigbrother_api, headers=self.HEADERS) as response:
            data = await response.json()
            self.update_cache(data)

    async def on_member_ban(self, guild: Guild, user: Union[User, Member]):
        if guild.id == GuildConfig.id and user.id in self.watched_users:
            url = f"{URLs.site_bigbrother_api}?user_id={user.id}"
            channel = self.watched_users[user.id]

            async with self.bot.http_session.delete(url, headers=self.HEADERS) as response:
                del self.watched_users[user.id]
                if response.status == 204:
                    await channel.send(
                        f"{Emojis.lemoneye2}:hammer: {user} got banned, so "
                        f"`BigBrother` will no longer relay their messages to {channel}"
                    )

                else:
                    data = await response.json()
                    reason = data.get('error_message', "no message provided")
                    await channel.send(
                        f"{Emojis.lemoneye2}:x: {user} got banned, but trying to remove them from"
                        f"BigBrother's user dictionary on the API returned an error: {reason}"
                    )

    async def on_message(self, msg: Message):
        if msg.author.id in self.watched_users:
            channel = self.watched_users[msg.author.id]
            relay_content = (f"{Emojis.lemoneye2} {msg.author} sent the following "
                             f"in {msg.channel.mention}: {msg.clean_content}")
            if msg.attachments:
                relay_content += f" (with {len(msg.attachments)} attachment(s))"

            await channel.send(relay_content)

    @command(name='bigbrother.watched()', aliases=('bigbrother.watched',))
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

    @command(name='bigbrother.watch()', aliases=('bigbrother.watch',))
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

    @command(name='bigbrother.unwatch()', aliases=('bigbrother.unwatch',))
    @with_role(Roles.owner, Roles.admin, Roles.moderator)
    async def unwatch_command(self, ctx: Context, user: User):
        """Stop relaying messages by the given `user`."""

        url = f"{URLs.site_bigbrother_api}?user_id={user.id}"
        async with self.bot.http_session.delete(url, headers=self.HEADERS) as response:
            if response.status == 204:
                await ctx.send(f":ok_hand: will no longer relay messages sent by {user}")

                if user.id in self.watched_users:
                    del self.watched_users[user.id]
                else:
                    log.warning(f"user {user.id} was unwatched but was not found in the cache")

            else:
                data = await response.json()
                reason = data.get('error_message', "no message provided")
                await ctx.send(f":x: the API returned an error: {reason}")


def setup(bot: Bot):
    bot.add_cog(BigBrother(bot))
    log.info("Cog loaded: BigBrother")
