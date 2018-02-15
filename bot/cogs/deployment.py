# coding=utf-8
from aiohttp import ClientSession
from discord import Embed, Colour

from discord.ext.commands import AutoShardedBot, Context, command

from bot.constants import ADMIN_ROLE, DEPLOY_BOT_KEY, DEPLOY_SITE_KEY, DEPLOY_URL, OWNER_ROLE, STATUS_URL
from bot.decorators import with_role


class Deployment:
    """
    Bot information commands
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    @command(name="redeploy()", aliases=["bot.redeploy", "bot.redeploy()", "redeploy"])
    @with_role(ADMIN_ROLE, OWNER_ROLE)
    async def redeploy(self, ctx: Context):
        """
        Trigger bot deployment on the server
        """

        with ClientSession() as session:
            result = await session.get(DEPLOY_URL, headers={"token": DEPLOY_BOT_KEY})

        if result == "True":
            await ctx.send(f"{ctx.author.mention} Bot deployment started.")
        else:
            await ctx.send(f"{ctx.author.mention} Bot deployment failed - check the logs!")

    @command(name="deploy_site()", aliases=["bot.deploy_site", "bot.deploy_site()", "deploy_site"])
    @with_role(ADMIN_ROLE, OWNER_ROLE)
    async def deploy_site(self, ctx: Context):
        """
        Trigger website deployment on the server
        """

        with ClientSession() as session:
            result = await session.get(DEPLOY_URL, headers={"token": DEPLOY_SITE_KEY})

        if result == "True":
            await ctx.send(f"{ctx.author.mention} Site deployment started.")
        else:
            await ctx.send(f"{ctx.author.mention} Site deployment failed - check the logs!")

    @command(name="uptimes()", aliases=["bot.uptimes", "bot.uptimes()", "uptimes"])
    @with_role(ADMIN_ROLE, OWNER_ROLE)
    async def uptimes(self, ctx: Context):
        """
        Check the various deployment uptimes for each service
        """

        with ClientSession() as session:
            response = await session.get(STATUS_URL)
            data = await response.json()

        embed = Embed(
            title="Service status",
            color=Colour.blurple()
        )

        for key, value in data.items():
            embed.add_field(
                name=key, value=value, inline=True
            )

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Deployment(bot))
    print("Cog loaded: Deployment")
