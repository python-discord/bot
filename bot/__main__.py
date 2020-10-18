import bot
from bot import constants
from bot.bot import Bot

bot.instance = Bot.create()
bot.instance.load_extensions()
bot.instance.run(constants.Bot.token)
