import logging
import unittest
from contextlib import contextmanager

import discord
from async_rediscache import RedisSession
from discord.ext import commands

from bot.log import get_logger
from tests import helpers


class _CaptureLogHandler(logging.Handler):
    """
    A logging handler capturing all (raw and formatted) logging output.
    """

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


class LoggingTestsMixin:
    """
    A mixin that defines additional test methods for logging behavior.

    This mixin relies on the availability of the `fail` attribute defined by the
    test classes included in Python's unittest method to signal test failure.
    """

    @contextmanager
    def assertNotLogs(self, logger=None, level=None, msg=None):  # noqa: N802
        """
        Asserts that no logs of `level` and higher were emitted by `logger`.

        You can specify a specific `logger`, the minimum `logging` level we want to watch and a
        custom `msg` to be added to the `AssertionError` if thrown. If the assertion fails, the
        recorded log records will be outputted with the `AssertionError` message. The context
        manager does not yield a live `look` into the logging records, since we use this context
        manager when we're testing under the assumption that no log records will be emitted.
        """
        if not isinstance(logger, logging.Logger):
            logger = get_logger(logger)

        if level:
            level = logging._nameToLevel.get(level, level)
        else:
            level = logging.INFO

        handler = _CaptureLogHandler()
        old_handlers = logger.handlers[:]
        old_level = logger.level
        old_propagate = logger.propagate

        logger.handlers = [handler]
        logger.setLevel(level)
        logger.propagate = False

        try:
            yield
        except Exception as exc:
            raise exc
        finally:
            logger.handlers = old_handlers
            logger.propagate = old_propagate
            logger.setLevel(old_level)

        if handler.records:
            level_name = logging.getLevelName(level)
            n_logs = len(handler.records)
            base_message = f"{n_logs} logs of {level_name} or higher were triggered on {logger.name}:\n"
            records = [str(record) for record in handler.records]
            record_message = "\n".join(records)
            standard_message = self._truncateMessage(base_message, record_message)
            msg = self._formatMessage(msg, standard_message)
            self.fail(msg)


class CommandTestCase(unittest.IsolatedAsyncioTestCase):
    """TestCase with additional assertions that are useful for testing Discord commands."""

    async def assertHasPermissionsCheck(  # noqa: N802
        self,
        cmd: commands.Command,
        permissions: dict[str, bool],
    ) -> None:
        """
        Test that `cmd` raises a `MissingPermissions` exception if author lacks `permissions`.

        Every permission in `permissions` is expected to be reported as missing. In other words, do
        not include permissions which should not raise an exception along with those which should.
        """
        # Invert permission values because it's more intuitive to pass to this assertion the same
        # permissions as those given to the check decorator.
        permissions = {k: not v for k, v in permissions.items()}

        ctx = helpers.MockContext()
        ctx.channel.permissions_for.return_value = discord.Permissions(**permissions)

        with self.assertRaises(commands.MissingPermissions) as cm:
            await cmd.can_run(ctx)

        self.assertCountEqual(permissions.keys(), cm.exception.missing_permissions)


class RedisTestCase(unittest.IsolatedAsyncioTestCase):
    """
    Use this as a base class for any test cases that require a redis session.

    This will prepare a fresh redis instance for each test function, and will
    not make any assertions on its own. Tests can mutate the instance as they wish.
    """

    session = None

    async def flush(self):
        """Flush everything from the redis database to prevent carry-overs between tests."""
        await self.session.client.flushall()

    async def asyncSetUp(self):
        self.session = await RedisSession(use_fakeredis=True).connect()
        await self.flush()

    async def asyncTearDown(self):
        if self.session:
            await self.session.client.close()
