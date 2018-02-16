# coding=utf-8
import os

from discord import Game
from discord.ext.commands import AutoShardedBot, when_mentioned_or

from bot.formatter import Formatter
from bot.utils import CaseInsensitiveDict

bot = AutoShardedBot(
    command_prefix=when_mentioned_or(
        ">>> self.", ">> self.", "> self.", "self.",
        ">>> bot.", ">> bot.", "> bot.", "bot.",
        ">>> ", ">> ", "> ",
        ">>>", ">>", ">"
    ),  # Order matters (and so do commas)
    game=Game(name="Help: bot.help()"),
    help_attrs={"aliases": ["help()"]},
    formatter=Formatter()
)

bot.cogs = CaseInsensitiveDict()

# Internal/debug
bot.load_extension("bot.cogs.logging")
bot.load_extension("bot.cogs.security")
bot.load_extension("bot.cogs.events")


# Commands, etc
bot.load_extension("bot.cogs.bot")
bot.load_extension("bot.cogs.deployment")
bot.load_extension("bot.cogs.fun")
bot.load_extension("bot.cogs.eval")
bot.load_extension("bot.cogs.verification")

bot.run(os.environ.get("BOT_TOKEN"))
