import logging
import os
import sys
from logging import handlers
from pathlib import Path

import coloredlogs
import sentry_sdk
from pydis_core.utils import logging as core_logging
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.redis import RedisIntegration

from bot import constants

get_logger = core_logging.get_logger


def setup() -> None:
    """Set up loggers."""
    root_log = get_logger()

    if constants.FILE_LOGS:
        log_file = Path("logs", "bot.log")
        log_file.parent.mkdir(exist_ok=True)
        file_handler = handlers.RotatingFileHandler(log_file, maxBytes=5242880, backupCount=7, encoding="utf8")
        file_handler.setFormatter(core_logging.log_format)
        root_log.addHandler(file_handler)

    if "COLOREDLOGS_LEVEL_STYLES" not in os.environ:
        coloredlogs.DEFAULT_LEVEL_STYLES = {
            **coloredlogs.DEFAULT_LEVEL_STYLES,
            "trace": {"color": 246},
            "critical": {"background": "red"},
            "debug": coloredlogs.DEFAULT_LEVEL_STYLES["info"]
        }

    if "COLOREDLOGS_LOG_FORMAT" not in os.environ:
        coloredlogs.DEFAULT_LOG_FORMAT = core_logging.log_format._fmt

    coloredlogs.install(level=core_logging.TRACE_LEVEL, logger=root_log, stream=sys.stdout)

    root_log.setLevel(logging.DEBUG if constants.DEBUG_MODE else logging.INFO)

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
            AsyncioIntegration(),
        ],
        release=f"bot@{constants.GIT_SHA}",
        enable_tracing=True,
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
            get_logger().setLevel(core_logging.TRACE_LEVEL)

        elif level_filter.startswith("!"):
            get_logger().setLevel(core_logging.TRACE_LEVEL)
            for logger_name in level_filter.strip("!,").split(","):
                get_logger(logger_name).setLevel(logging.DEBUG)

        else:
            for logger_name in level_filter.strip(",").split(","):
                get_logger(logger_name).setLevel(core_logging.TRACE_LEVEL)
