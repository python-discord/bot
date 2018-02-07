# coding=utf-8
import os

from discord import Game
from discord.ext.commands import AutoShardedBot, when_mentioned_or

bot = AutoShardedBot(
    command_prefix=when_mentioned_or(
        ">>> self." ">> self.", "> self.", "self.", ">>> ", ">> ", "> ", ">>>", ">>", ">"
    ),  # Order matters
    game=Game(name=">>> help")
)

# Internal/debug
bot.load_extension("bot.cogs.logging")
bot.load_extension("bot.cogs.security")
bot.load_extension("bot.cogs.events")

# Owner-only
bot.load_extension("bot.cogs.eval")

# Commands, etc
bot.load_extension("bot.cogs.bot")
bot.load_extension("bot.cogs.verification")

bot.run(os.environ.get("BOT_TOKEN"))
