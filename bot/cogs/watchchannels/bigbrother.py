import logging
from collections import ChainMap
from typing import Union

from discord import Color, Embed, User
from discord.ext.commands import Context, group

from bot.constants import Channels, Roles, Webhooks
from bot.decorators import with_role
from bot.utils.moderation import post_infraction
from .watchchannel import WatchChannel, proxy_user

log = logging.getLogger(__name__)


class BigBrother(WatchChannel):
    """Monitors users by relaying their messages to a watch channel to assist with moderation."""

    def __init__(self, bot) -> None:
        super().__init__(
            bot,
            destination=Channels.big_brother_logs,
            webhook_id=Webhooks.big_brother,
            api_endpoint='bot/infractions',
            api_default_params={'active': 'true', 'type': 'watch', 'ordering': '-inserted_at'},
            logger=log
        )

    @group(name='bigbrother', aliases=('bb',), invoke_without_command=True)
    @with_role(Roles.owner, Roles.admin, Roles.moderator)
    async def bigbrother_group(self, ctx: Context) -> None:
        """Monitors users by relaying their messages to the BigBrother watch channel."""
        await ctx.invoke(self.bot.get_command("help"), "bigbrother")

    @bigbrother_group.command(name='watched', aliases=('all', 'list'))
    @with_role(Roles.owner, Roles.admin, Roles.moderator)
    async def watched_command(self, ctx: Context, update_cache: bool = True) -> None:
        """
        Shows the users that are currently being monitored in BigBrother.

        The optional kwarg `update_cache` can be used to update the user
        cache using the API before listing the users.
        """
        await self.list_watched_users(ctx, update_cache)

    @bigbrother_group.command(name='watch', aliases=('w',))
    @with_role(Roles.owner, Roles.admin, Roles.moderator)
    async def watch_command(self, ctx: Context, user: Union[User, proxy_user], *, reason: str) -> None:
        """
        Relay messages sent by the given `user` to the `#big-brother-logs` channel.

        A `reason` for adding the user to BigBrother is required and will displayed
        in the header when relaying messages of this user to the watchchannel.
        """
        if user.bot:
            await ctx.send(f":x: I'm sorry {ctx.author}, I'm afraid I can't do that. I only watch humans.")
            return

        if not await self.fetch_user_cache():
            await ctx.send(f":x: Updating the user cache failed, can't watch user {user}")
            return

        if user.id in self.watched_users:
            await ctx.send(":x: The specified user is already being watched.")
            return

        response = await post_infraction(
            ctx, user, type='watch', reason=reason, hidden=True
        )

        if response is not None:
            self.watched_users[user.id] = response
            await ctx.send(f":white_check_mark: Messages sent by {user} will now be relayed to BigBrother.")

    @bigbrother_group.command(name='unwatch', aliases=('uw',))
    @with_role(Roles.owner, Roles.admin, Roles.moderator)
    async def unwatch_command(self, ctx: Context, user: Union[User, proxy_user], *, reason: str) -> None:
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

            await self.bot.api_client.patch(
                f"{self.api_endpoint}/{infraction['id']}",
                json={'active': False}
            )

            await post_infraction(ctx, user, type='watch', reason=f"Unwatched: {reason}", hidden=True, active=False)

            await ctx.send(f":white_check_mark: Messages sent by {user} will no longer be relayed.")

            self._remove_user(user.id)
        else:
            await ctx.send(":x: The specified user is currently not being watched.")
