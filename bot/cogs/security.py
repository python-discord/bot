# coding=utf-8
from discord.ext.commands import AutoShardedBot, Context

__author__ = "Gareth Coles"


class Security:
    """
    Security-related helpers
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot
        self.bot.check(self.check_not_bot)

    async def check_not_bot(self, ctx: Context):
        return not ctx.author.bot


def setup(bot):
    bot.add_cog(Security(bot))
    print("Cog loaded: Security")
