import logging

from discord import Color, Embed, User
from discord.ext.commands import Context, group

from bot.cogs.bigbrother import BigBrother, Roles
from bot.constants import Channels
from bot.decorators import with_role
from bot.pagination import LinePaginator


log = logging.getLogger(__name__)


class Nominations(BigBrother):
    """Monitor potential helpers, NSA-style."""

    async def on_ready(self):
        """Retrieve nominees from the API."""

        self.channel = self.bot.get_channel(Channels.talent_pool)
        if self.channel is None:
            log.error("Cannot find talent pool channel. Cannot watch nominees.")
        else:
            nominations = await self.bot.api_client.get(
                'bot/nominations',
                params={'active': 'true'}
            )
            self.update_cache(nominations)

    async def on_member_ban(self, *_):
        pass

    @group(name='nominations', aliases=('n',), invoke_without_command=True)
    @with_role(Roles.owner, Roles.admin, Roles.moderator)
    async def bigbrother_group(self, ctx: Context):
        """Nominate helpers, NSA-style."""

        await ctx.invoke(self.bot.get_command("help"), "nominations")

    @bigbrother_group.command(name='nominated', aliases=('nominees', 'all'))
    @with_role(Roles.owner, Roles.admin, Roles.moderator)
    async def watched_command(self, ctx: Context, from_cache: bool = True):
        if from_cache:
            lines = tuple(f"• <@{user_id}>" for user_id in self.watched_users)

        else:
            active_nominations = await self.bot.api_client.get(
                'bot/nominations',
                params={'active': 'true'}
            )
            self.update_cache(active_nominations)
            lines = tuple(
                f"• <@{entry['user']}>: {entry['reason'] or '*no reason provided*'}"
                for entry in active_nominations
            )

        await LinePaginator.paginate(
            lines or ("There's nothing here yet.",),
            ctx,
            Embed(
                title="Nominated users" + " (cached)" * from_cache,
                color=Color.blue()
            ),
            empty=False
        )

    @bigbrother_group.command(name='nominate', aliases=('n',))
    @with_role(Roles.owner, Roles.admin, Roles.moderator)
    async def watch_command(self, ctx: Context, user: User, *, reason: str):
        """Talent pool the given `user`."""

        active_nominations = await self.bot.api_client.get(
            'bot/nominations/' + str(user.id),
        )
        if active_nominations:
            active_nominations = await self.bot.api_client.put(
                'bot/nominations/' + str(user.id),
                json={'active': True}
            )
            await ctx.send(":ok_hand: user's watch was updated")

        else:
            active_nominations = await self.bot.api_client.post(
                'bot/nominations/' + str(user.id),
                json={
                    'active': True,
                    'author': ctx.author.id,
                    'reason': reason,
                }
            )
            self.watched_users.add(user.id)
            await ctx.send(":ok_hand: user added to talent pool")

    @bigbrother_group.command(name='unnominate', aliases=('un',))
    @with_role(Roles.owner, Roles.admin, Roles.moderator)
    async def unwatch_command(self, ctx: Context, user: User):
        """Stop talent pooling the given `user`."""

        nomination = await self.bot.api_client.get(
            'bot/nominations/' + str(user.id)
        )

        if not nomination['active']:
            await ctx.send(":x: the nomination is already inactive")

        else:
            await self.bot.api_client.put(
                'bot/nominations/' + str(user.id),
                json={'active': False}
            )
            self.watched_users.remove(user.id)
            if user.id in self.channel_queues:
                del self.channel_queues[user.id]
            await ctx.send(f":ok_hand: {user} is no longer part of the talent pool")


def setup(bot):
    bot.add_cog(Nominations(bot))
    log.info("Cog loaded: Nominations")
