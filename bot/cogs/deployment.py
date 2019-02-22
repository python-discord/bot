import logging

from discord import Colour, Embed
from discord.ext.commands import Bot, Context, command, group

from bot.constants import Keys, MODERATION_ROLES, Roles, URLs
from bot.decorators import with_role

log = logging.getLogger(__name__)


class Deployment:
    """
    Bot information commands
    """

    def __init__(self, bot: Bot):
        self.bot = bot

    @group(name='redeploy', invoke_without_command=True)
    @with_role(*MODERATION_ROLES)
    async def redeploy_group(self, ctx: Context):
        """Redeploy the bot or the site."""

        await ctx.invoke(self.bot.get_command("help"), "redeploy")

    @redeploy_group.command(name='bot')
    @with_role(Roles.admin, Roles.owner, Roles.devops)
    async def bot_command(self, ctx: Context):
        """
        Trigger bot deployment on the server - will only redeploy if there were changes to deploy
        """

        response = await self.bot.http_session.get(URLs.deploy, headers={"token": Keys.deploy_bot})
        result = await response.text()

        if result == "True":
            log.debug(f"{ctx.author} triggered deployment for bot. Deployment was started.")
            await ctx.send(f"{ctx.author.mention} Bot deployment started.")
        else:
            log.error(f"{ctx.author} triggered deployment for bot. Deployment failed to start.")
            await ctx.send(f"{ctx.author.mention} Bot deployment failed - check the logs!")

    @redeploy_group.command(name='site')
    @with_role(Roles.admin, Roles.owner, Roles.devops)
    async def site_command(self, ctx: Context):
        """
        Trigger website deployment on the server - will only redeploy if there were changes to deploy
        """

        response = await self.bot.http_session.get(URLs.deploy, headers={"token": Keys.deploy_bot})
        result = await response.text()

        if result == "True":
            log.debug(f"{ctx.author} triggered deployment for site. Deployment was started.")
            await ctx.send(f"{ctx.author.mention} Site deployment started.")
        else:
            log.error(f"{ctx.author} triggered deployment for site. Deployment failed to start.")
            await ctx.send(f"{ctx.author.mention} Site deployment failed - check the logs!")

    @command(name='uptimes')
    @with_role(Roles.admin, Roles.owner, Roles.devops)
    async def uptimes_command(self, ctx: Context):
        """
        Check the various deployment uptimes for each service
        """

        log.debug(f"{ctx.author} requested service uptimes.")
        response = await self.bot.http_session.get(URLs.status)
        data = await response.json()

        embed = Embed(
            title="Service status",
            color=Colour.blurple()
        )

        for obj in data:
            key, value = list(obj.items())[0]

            embed.add_field(
                name=key, value=value, inline=True
            )

        log.debug("Uptimes retrieved and parsed, returning data.")
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Deployment(bot))
    log.info("Cog loaded: Deployment")
