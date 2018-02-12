# coding=utf-8
from discord.ext.commands import AutoShardedBot

from bot.constants import DEVLOG_CHANNEL


class Logging:
    """
    Debug logging module
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    async def on_ready(self):
        print("Connected!")
        await self.bot.get_channel(DEVLOG_CHANNEL).send("Connected!")


def setup(bot):
    bot.add_cog(Logging(bot))
    print("Cog loaded: Logging")
