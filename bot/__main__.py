import bot
from bot import constants
from bot.bot import Bot
from bot.log import setup_sentry

setup_sentry()

bot.instance = Bot.create()
bot.instance.load_extensions()
bot.instance.run(constants.Bot.token)
