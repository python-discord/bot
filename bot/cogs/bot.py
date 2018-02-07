# coding=utf-8
from discord import Embed
from discord.ext.commands import AutoShardedBot, Context, group

from dulwich.repo import Repo

from bot.decorators import is_verified

__author__ = "Gareth Coles"


class Bot:
    """
    Bot information commands
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    @group(invoke_without_command=True, name="bot")
    @is_verified()
    async def bot_group(self, ctx: Context):
        """
        Bot informational commands
        """

        await ctx.invoke(self.bot.get_command("help"), "bot")

    @bot_group.command(aliases=["about"])
    @is_verified()
    async def info(self, ctx: Context):
        """
        Get information about the current bot
        """

        embed = Embed(
            description="A utility bot designed just for the Python server! Try `>>> help` for more info.",
            url="https://github.com/discord-python/bot"
        )

        repo = Repo(".")
        sha = repo[repo.head()].sha().hexdigest()

        embed.add_field(name="Total Users", value=str(len(self.bot.users)))
        embed.add_field(name="Git SHA", value=str(sha)[:7])

        embed.set_author(
            name="Python Bot",
            url="https://github.com/discord-python/bot",
            icon_url="https://raw.githubusercontent.com/discord-python/branding/master/logos/logo_circle.png"
        )

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Bot(bot))
    print("Cog loaded: Bot")
