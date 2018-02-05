# coding=utf-8
import os

from discord.ext.commands import AutoShardedBot, when_mentioned_or

bot = AutoShardedBot(command_prefix=when_mentioned_or(">>> ", ">>>"))

# Internal/debug
bot.load_extension("bot.cogs.logging")
bot.load_extension("bot.cogs.security")
bot.load_extension("bot.cogs.events")

# Owner-only
bot.load_extension("bot.cogs.eval")

# Commands
bot.load_extension("bot.cogs.bot")

bot.run(os.environ.get("BOT_TOKEN"))
