from discord.ext import commands

from bot.bot import Bot


class HelpChannels(commands.Cog):
    """Manage the help channel system of the guild."""


def setup(bot: Bot) -> None:
    """Load the HelpChannels cog."""
    bot.add_cog(HelpChannels(bot))
