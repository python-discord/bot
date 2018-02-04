# coding=utf-8
from discord import Embed
from discord.ext.commands import AutoShardedBot, group, Context

__author__ = "Gareth Coles"


class Bot:
    """
    Bot information commands
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    @group(invoke_without_command=True, name="bot")
    async def bot_group(self, ctx: Context):
        """
        Bot information commands
        """

        await ctx.invoke(self.bot.get_command("help"), "bot")

    @bot_group.command(aliases=["about"])
    async def info(self, ctx: Context):
        """
        Get information about the current bot
        """

        if not hasattr(self.bot, "shard_id") or self.bot.shard_id is None:
            embed = Embed(
                description="A utility bot designed just for the Python server!. Try `>>> help` for more info.\n\n"
                            "**Currently __not sharded__.**",
                url="https://github.com/discord-python/bot"
            )
        else:
            embed = Embed(
                description="A utility bot designed just for the Python server! Try `>>> help` for more info.",
                url="https://github.com/discord-python/bot"
            )
            embed.add_field(
                name="Total Shards", value=self.bot.shard_count
            )
            embed.add_field(
                name="Current Shard", value=self.bot.shard_id
            )

        embed.add_field(name="Visible Guilds", value=str(len(self.bot.guilds)))
        embed.add_field(name="Visible Users", value=str(len(self.bot.users)))

        embed.set_author(
            name="Python Bot",
            url="https://github.com/discord-python/bot",
            icon_url="https://avatars3.githubusercontent.com/u/36101493?s=200&v=4"
        )

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Bot(bot))
    print("Cog loaded: Bot")
