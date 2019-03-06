import logging
import os
import sys
from logging import Logger, StreamHandler, handlers

from logmatic import JsonFormatter

logging.TRACE = 5
logging.addLevelName(logging.TRACE, "TRACE")


def monkeypatch_trace(self, msg, *args, **kwargs):
    """
    Log 'msg % args' with severity 'TRACE'.

    To pass exception information, use the keyword argument exc_info with
    a true value, e.g.

    logger.trace("Houston, we have an %s", "interesting problem", exc_info=1)
    """
    if self.isEnabledFor(logging.TRACE):
        self._log(logging.TRACE, msg, args, **kwargs)


Logger.trace = monkeypatch_trace

# Set up logging
logging_handlers = []

# We can't import this yet, so we have to define it ourselves
DEBUG_MODE = True if 'local' in os.environ.get("SITE_URL", "local") else False


if DEBUG_MODE:
    logging_handlers.append(StreamHandler(stream=sys.stdout))

    json_handler = logging.FileHandler(filename="log.json", mode="w")
    json_handler.formatter = JsonFormatter()
    logging_handlers.append(json_handler)
else:

    logdir = "log"
    logfile = logdir+os.sep+"bot.log"
    megabyte = 1048576

    if not os.path.exists(logdir):
        os.makedirs(logdir)

    filehandler = handlers.RotatingFileHandler(logfile, maxBytes=(megabyte*5), backupCount=7)
    logging_handlers.append(filehandler)

    json_handler = logging.StreamHandler(stream=sys.stdout)
    json_handler.formatter = JsonFormatter()
    logging_handlers.append(json_handler)


logging.basicConfig(
    format="%(asctime)s pd.beardfist.com Bot: | %(name)30s | %(levelname)8s | %(message)s",
    datefmt="%b %d %H:%M:%S",
    level=logging.TRACE if DEBUG_MODE else logging.INFO,
    handlers=logging_handlers
)

log = logging.getLogger(__name__)


for key, value in logging.Logger.manager.loggerDict.items():
    # Force all existing loggers to the correct level and handlers
    # This happens long before we instantiate our loggers, so
    # those should still have the expected level

    if key == "bot":
        continue

    if not isinstance(value, logging.Logger):
        # There might be some logging.PlaceHolder objects in there
        continue

    if DEBUG_MODE:
        value.setLevel(logging.DEBUG)
    else:
        value.setLevel(logging.INFO)

    for handler in value.handlers.copy():
        value.removeHandler(handler)

    for handler in logging_handlers:
        value.addHandler(handler)


# Silence irrelevant loggers
logging.getLogger("aio_pika").setLevel(logging.ERROR)
logging.getLogger("discord").setLevel(logging.ERROR)
logging.getLogger("websockets").setLevel(logging.ERROR)
