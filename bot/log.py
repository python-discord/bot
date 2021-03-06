import logging
import os
import sys
from logging import Logger, StreamHandler, handlers
from pathlib import Path

import coloredlogs
import sentry_sdk
from pythonjsonlogger import jsonlogger
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.redis import RedisIntegration

from bot import constants

TRACE_LEVEL = 5

PROD_FIELDS = [
    "asctime",
    "name",
    "levelname",
    "message",
    "funcName",
    "filename"
]


def setup() -> None:
    """Set up loggers."""
    logging.TRACE = TRACE_LEVEL
    logging.addLevelName(TRACE_LEVEL, "TRACE")
    Logger.trace = _monkeypatch_trace

    log_level = TRACE_LEVEL if constants.DEBUG_MODE else logging.INFO
    format_string = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
    log_format = logging.Formatter(format_string)

    log_file = Path("logs", "bot.log")
    log_file.parent.mkdir(exist_ok=True)
    file_handler = handlers.RotatingFileHandler(log_file, maxBytes=5242880, backupCount=7, encoding="utf8")
    file_handler.setFormatter(log_format)

    root_log = logging.getLogger()
    root_log.setLevel(log_level)
    root_log.addHandler(file_handler)

    if constants.DEBUG_MODE:
        if "COLOREDLOGS_LEVEL_STYLES" not in os.environ:
            coloredlogs.DEFAULT_LEVEL_STYLES = {
                **coloredlogs.DEFAULT_LEVEL_STYLES,
                "trace": {"color": 246},
                "critical": {"background": "red"},
                "debug": coloredlogs.DEFAULT_LEVEL_STYLES["info"]
            }

        if "COLOREDLOGS_LOG_FORMAT" not in os.environ:
            coloredlogs.DEFAULT_LOG_FORMAT = format_string

        if "COLOREDLOGS_LOG_LEVEL" not in os.environ:
            coloredlogs.DEFAULT_LOG_LEVEL = log_level

        coloredlogs.install(logger=root_log, stream=sys.stdout)
    else:
        json_format = " ".join([f"%({field})s" for field in PROD_FIELDS])
        stream_handler = StreamHandler()
        formatter = jsonlogger.JsonFormatter(json_format)
        stream_handler.setFormatter(formatter)
        root_log.addHandler(stream_handler)

    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("chardet").setLevel(logging.WARNING)
    logging.getLogger("async_rediscache").setLevel(logging.WARNING)

    # Set back to the default of INFO even if asyncio's debug mode is enabled.
    logging.getLogger("asyncio").setLevel(logging.INFO)


def setup_sentry() -> None:
    """Set up the Sentry logging integrations."""
    sentry_logging = LoggingIntegration(
        level=logging.DEBUG,
        event_level=logging.WARNING
    )

    sentry_sdk.init(
        dsn=constants.Bot.sentry_dsn,
        integrations=[
            sentry_logging,
            RedisIntegration(),
        ],
        release=f"bot@{constants.GIT_SHA}"
    )


def _monkeypatch_trace(self: logging.Logger, msg: str, *args, **kwargs) -> None:
    """
    Log 'msg % args' with severity 'TRACE'.

    To pass exception information, use the keyword argument exc_info with
    a true value, e.g.

    logger.trace("Houston, we have an %s", "interesting problem", exc_info=1)
    """
    if self.isEnabledFor(TRACE_LEVEL):
        self._log(TRACE_LEVEL, msg, args, **kwargs)
