import aiohttp

import bot
from bot import constants
from bot.bot import Bot, StartupError
from bot.log import get_logger, setup_sentry

setup_sentry()

try:
    bot.instance = Bot.create()
    bot.instance.load_extensions()
    bot.instance.run(constants.Bot.token)
except StartupError as e:
    message = "Unknown Startup Error Occurred."
    if isinstance(e.exception, (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError)):
        message = "Could not connect to site API. Is it running?"
    elif isinstance(e.exception, OSError):
        message = "Could not connect to Redis. Is it running?"

    # The exception is logged with an empty message so the actual message is visible at the bottom
    log = get_logger("bot")
    log.fatal("", exc_info=e.exception)
    log.fatal(message)

    exit(69)
