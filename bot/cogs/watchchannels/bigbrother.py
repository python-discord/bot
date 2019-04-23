import logging
from collections import ChainMap

from discord import Color, Embed, User
from discord.ext.commands import Context, group

from bot.constants import (
    Channels, Roles
)
from bot.decorators import with_role
from bot.utils.moderation import post_infraction
from .watchchannel import WatchChannel

log = logging.getLogger(__name__)


class BigBrother(WatchChannel):
    """User monitoring to assist with moderation"""

    def __init__(self, bot):
        super().__init__(bot)
        self.log = log

        self.destination = Channels.big_brother_logs
        self.webhook_id = 569096053333164052
        self.api_endpoint = 'bot/infractions'
        self.api_default_params = {'active': 'true', 'type': 'watch'}

    @group(name='bigbrother', aliases=('bb',), invoke_without_command=True)
    @with_role(Roles.owner, Roles.admin, Roles.moderator)
    async def bigbrother_group(self, ctx: Context) -> None:
        """Monitors users by relaying their messages to the BigBrother watch channel"""

        await ctx.invoke(self.bot.get_command("help"), "bigbrother")

    @bigbrother_group.command(name='watched', aliases=('all',))
    @with_role(Roles.owner, Roles.admin, Roles.moderator)
    async def watched_command(self, ctx: Context, update_cache: bool = False) -> None:
        """
        Shows the users that are currently being monitored in BigBrother.

        The optional kwarg `update_cache` can be used to update the user
        cache using the API before listing the users.
        """

        await self.list_watched_users(ctx, update_cache)

    @bigbrother_group.command(name='watch', aliases=('w',))
    @with_role(Roles.owner, Roles.admin, Roles.moderator)
    async def watch_command(self, ctx: Context, user: User, *, reason: str) -> None:
        """
        Relay messages sent by the given `user` to the `#big-brother-logs` channel.

        A `reason` for adding the user to BigBrother is required and will displayed
        in the header when relaying messages of this user to the watchchannel.
        """

        await self.fetch_user_cache()

        if user.id in self.watched_users:
            e = Embed(
                description=":x: **The specified user is already being watched**",
                color=Color.red()
            )
            return await ctx.send(embed=e)

        response = await post_infraction(
            ctx, user, type='watch', reason=reason, hidden=True
        )
        if response is not None:
            self.watched_users[user.id] = response
            e = Embed(
                description=f":white_check_mark: **Messages sent by {user} will now be relayed**",
                color=Color.green()
            )
            return await ctx.send(embed=e)

    @bigbrother_group.command(name='unwatch', aliases=('uw',))
    @with_role(Roles.owner, Roles.admin, Roles.moderator)
    async def unwatch_command(self, ctx: Context, user: User, *, reason: str) -> None:
        """Stop relaying messages by the given `user`."""

        active_watches = await self.bot.api_client.get(
            self.api_endpoint,
            params=ChainMap(
                self.api_default_params,
                {"user__id": str(user.id)}
            )
        )
        if active_watches:
            [infraction] = active_watches
            log.trace(infraction)
            await self.bot.api_client.patch(
                f"{self.api_endpoint}/{infraction['id']}",
                json={'active': False}
            )
            await post_infraction(
                ctx, user, type='watch', reason=f"Unwatched: {reason}", hidden=True, active=False
            )
            e = Embed(
                description=f":white_check_mark: **Messages sent by {user} will no longer be relayed**",
                color=Color.green()
            )
            return await ctx.send(embed=e)
            self.watched_users.pop(str(user.id), None)
            self.message_queue.pop(str(user.id), None)
            self.consumption_queue.pop(str(user.id), None)
        else:
            e = Embed(
                description=":x: **The specified user is currently not being watched**",
                color=Color.red()
            )
            return await ctx.send(embed=e)
