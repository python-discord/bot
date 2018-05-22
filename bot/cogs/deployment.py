import logging

from discord import Colour, Embed
from discord.ext.commands import AutoShardedBot, Context, command

from bot.constants import Keys, Roles, URLs
from bot.decorators import with_role

log = logging.getLogger(__name__)


class Deployment:
    """
    Bot information commands
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    @command(name="redeploy()", aliases=["bot.redeploy", "bot.redeploy()", "redeploy"])
    @with_role(Roles.admin, Roles.owner, Roles.devops)
    async def redeploy(self, ctx: Context):
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

    @command(name="deploy_site()", aliases=["bot.deploy_site", "bot.deploy_site()", "deploy_site"])
    @with_role(Roles.admin, Roles.owner, Roles.devops)
    async def deploy_site(self, ctx: Context):
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

    @command(name="uptimes()", aliases=["bot.uptimes", "bot.uptimes()", "uptimes"])
    @with_role(Roles.admin, Roles.owner, Roles.devops)
    async def uptimes(self, ctx: Context):
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
