import logging
import os
import sys
from logging import Logger, StreamHandler, handlers
from pathlib import Path

TRACE_LEVEL = logging.TRACE = 5
logging.addLevelName(TRACE_LEVEL, "TRACE")


def monkeypatch_trace(self: logging.Logger, msg: str, *args, **kwargs) -> None:
    """
    Log 'msg % args' with severity 'TRACE'.

    To pass exception information, use the keyword argument exc_info with
    a true value, e.g.

    logger.trace("Houston, we have an %s", "interesting problem", exc_info=1)
    """
    if self.isEnabledFor(TRACE_LEVEL):
        self._log(TRACE_LEVEL, msg, args, **kwargs)


Logger.trace = monkeypatch_trace

DEBUG_MODE = 'local' in os.environ.get("SITE_URL", "local")

log_format = logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")

stream_handler = StreamHandler(stream=sys.stdout)
stream_handler.setFormatter(log_format)

log_file = Path("logs", "bot.log")
log_file.parent.mkdir(exist_ok=True)
file_handler = handlers.RotatingFileHandler(log_file, maxBytes=5242880, backupCount=7)
file_handler.setFormatter(log_format)

root_log = logging.getLogger()
root_log.setLevel(TRACE_LEVEL if DEBUG_MODE else logging.INFO)
root_log.addHandler(stream_handler)
root_log.addHandler(file_handler)

logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger(__name__)
