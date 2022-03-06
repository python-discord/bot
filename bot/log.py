import logging
import os
import sys
from logging import Logger, handlers
from pathlib import Path
from typing import Optional, TYPE_CHECKING, cast

import coloredlogs
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.redis import RedisIntegration

from bot import constants

TRACE_LEVEL = 5


if TYPE_CHECKING:
    LoggerClass = Logger
else:
    LoggerClass = logging.getLoggerClass()


class CustomLogger(LoggerClass):
    """Custom implementation of the `Logger` class with an added `trace` method."""

    def trace(self, msg: str, *args, **kwargs) -> None:
        """
        Log 'msg % args' with severity 'TRACE'.

        To pass exception information, use the keyword argument exc_info with
        a true value, e.g.

        logger.trace("Houston, we have an %s", "interesting problem", exc_info=1)
        """
        if self.isEnabledFor(TRACE_LEVEL):
            self.log(TRACE_LEVEL, msg, *args, **kwargs)


def get_logger(name: Optional[str] = None) -> CustomLogger:
    """Utility to make mypy recognise that logger is of type `CustomLogger`."""
    return cast(CustomLogger, logging.getLogger(name))


def setup() -> None:
    """Set up loggers."""
    logging.TRACE = TRACE_LEVEL
    logging.addLevelName(TRACE_LEVEL, "TRACE")
    logging.setLoggerClass(CustomLogger)

    root_log = get_logger()

    format_string = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
    log_format = logging.Formatter(format_string)

    if constants.FILE_LOGS:
        log_file = Path("logs", "bot.log")
        log_file.parent.mkdir(exist_ok=True)
        file_handler = handlers.RotatingFileHandler(log_file, maxBytes=5242880, backupCount=7, encoding="utf8")
        file_handler.setFormatter(log_format)
        root_log.addHandler(file_handler)

    if "COLOREDLOGS_LEVEL_STYLES" not in os.environ:
        coloredlogs.DEFAULT_LEVEL_STYLES = {
            **coloredlogs.DEFAULT_LEVEL_STYLES,
            "trace": {"color": 246},
            "critical": {"background": "red"},
            "debug": coloredlogs.DEFAULT_LEVEL_STYLES["info"]
        }

    if "COLOREDLOGS_LOG_FORMAT" not in os.environ:
        coloredlogs.DEFAULT_LOG_FORMAT = format_string

    coloredlogs.install(level=TRACE_LEVEL, logger=root_log, stream=sys.stdout)

    root_log.setLevel(logging.DEBUG if constants.DEBUG_MODE else logging.INFO)
    get_logger("disnake").setLevel(logging.WARNING)
    get_logger("websockets").setLevel(logging.WARNING)
    get_logger("chardet").setLevel(logging.WARNING)
    get_logger("async_rediscache").setLevel(logging.WARNING)

    # Set back to the default of INFO even if asyncio's debug mode is enabled.
    get_logger("asyncio").setLevel(logging.INFO)

    _set_trace_loggers()


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


def _set_trace_loggers() -> None:
    """
    Set loggers to the trace level according to the value from the BOT_TRACE_LOGGERS env var.

    When the env var is a list of logger names delimited by a comma,
    each of the listed loggers will be set to the trace level.

    If this list is prefixed with a "!", all of the loggers except the listed ones will be set to the trace level.

    Otherwise if the env var begins with a "*",
    the root logger is set to the trace level and other contents are ignored.
    """
    level_filter = constants.Bot.trace_loggers
    if level_filter:
        if level_filter.startswith("*"):
            get_logger().setLevel(TRACE_LEVEL)

        elif level_filter.startswith("!"):
            get_logger().setLevel(TRACE_LEVEL)
            for logger_name in level_filter.strip("!,").split(","):
                get_logger(logger_name).setLevel(logging.DEBUG)

        else:
            for logger_name in level_filter.strip(",").split(","):
                get_logger(logger_name).setLevel(TRACE_LEVEL)
