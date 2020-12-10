import logging

from discord import Member, Role
from discord.ext.commands import Cog, Context, command, has_any_role

from bot.bot import Bot
from bot.constants import Emojis, Guild, MODERATION_ROLES, Roles

log = logging.getLogger(__name__)


class Verify(Cog):
    """Command for applying verification roles."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.developer_role: Role = None

    @Cog.listener()
    async def on_ready(self) -> None:
        """Sets `self.developer_role` to the Role object once the bot is online."""
        await self.bot.wait_until_guild_available()
        self.developer_role = self.bot.get_guild(Guild.id).get_role(Roles.verified)

    @command(name='verify')
    @has_any_role(*MODERATION_ROLES)
    async def apply_developer_role(self, ctx: Context, user: Member) -> None:
        """Command for moderators to apply the Developer role to any user."""
        log.trace(f'verify command called by {ctx.author} for {user.id}.')
        if self.developer_role is None:
            await self.on_ready()

        if self.developer_role in user.roles:
            log.trace(f'{user.id} is already a developer, aborting.')
            await ctx.send(f'{Emojis.cross_mark} {user} is already a developer.')
            return

        await user.add_roles(self.developer_role)
        log.trace(f'Developer role successfully applied to {user.id}')
        await ctx.send(f'{Emojis.check_mark} Developer role role applied to {user}.')


def setup(bot: Bot) -> None:
    """Load the Verify cog."""
    bot.add_cog(Verify(bot))
