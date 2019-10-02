import logging
import unittest
from contextlib import contextmanager


class _CaptureLogHandler(logging.Handler):
    """
    A logging handler capturing all (raw and formatted) logging output.
    """

    def __init__(self):
        super().__init__()
        self.records = []

    def flush(self):
        pass

    def emit(self, record):
        self.records.append(record)


class LoggingTestCase(unittest.TestCase):
    """TestCase subclass that adds more logging assertion tools."""

    @contextmanager
    def assertNotLogs(self, logger=None, level=None, msg=None):
        """
        Asserts that no logs of `level` and higher were emitted by `logger`.

        You can specify a specific `logger`, the minimum `logging` level we want to watch and a
        custom `msg` to be added to the `AssertionError` if thrown. If the assertion fails, the
        recorded log records will be outputted with the `AssertionError` message. The context
        manager does not yield a live `look` into the logging records, since we use this context
        manager when we're testing under the assumption that no log records will be emitted.
        """
        if not isinstance(logger, logging.Logger):
            logger = logging.getLogger(logger)

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
