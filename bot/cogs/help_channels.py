import json
from pathlib import Path

from discord.ext import commands

from bot.bot import Bot


with Path("bot/resources/elements.json").open(encoding="utf-8") as elements_file:
    ELEMENTS = json.load(elements_file)


class HelpChannels(commands.Cog):
    """Manage the help channel system of the guild."""


def setup(bot: Bot) -> None:
    """Load the HelpChannels cog."""
    bot.add_cog(HelpChannels(bot))
