# coding=utf-8
from discord.ext.commands import AutoShardedBot
from discord import Embed

from bot.constants import DEVLOG_CHANNEL


class Logging:
    """
    Debug logging module
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot

    async def on_ready(self):
        print("Connected!")

        embed = Embed(title="Python", description="Connected!")
        embed.set_thumbnail("https://raw.githubusercontent.com/discord-python/branding/master/logos/logo_circle.png") 
        
        await self.bot.get_channel(DEVLOG_CHANNEL).send(embed=embed)


def setup(bot):
    bot.add_cog(Logging(bot))
    print("Cog loaded: Logging")
