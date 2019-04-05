import logging
from discord.ext.commands import Bot, command, Context, BadArgument, MissingPermissions
from discord import Role
from bot.decorators import with_role
from bot.constants import MODERATION_ROLES

log = logging.getLogger(__name__)


class Ping:
    """
    Pinging a role so that there
    is no chance of it getting left un-pinged.
    Sorry guys <3 - aj
    """

    def __init__(self, bot: Bot):
        self.bot = bot

    @command
    @with_role(*MODERATION_ROLES)
    async def ping(self, ctx: Context, role: Role):
        """
        Pings a role

        **`role`**: Accepts role mention, ID etc.
        """
        if role.mentionable:
            await ctx.send("That role is already mentionable.")
            return

        await role.edit(mentionable=True)   # make the role ping-able
        await ctx.send(f"{role.mention}")   # fix this message. I'm dumb and don't have the right words. Ping the role
        await role.edit(mentionable=False)  # make the role un-ping-able
        return

    @ping.error
    async def ping_error(self, ctx, error):
        if isinstance(error, BadArgument):
            await ctx.send("That's not a role in this guild!")
            return

        if isinstance(error, MissingPermissions):
            await ctx.send("I don't have permission to edit that role!")
            return

        log.error(error)


def setup(bot: Bot):
    bot.add_cog(Ping(bot))
    log.info("Cog loaded: Ping")
