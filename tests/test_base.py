import logging
import unittest.mock

from bot.log import get_logger
from tests.base import LoggingTestsMixin, _CaptureLogHandler


class LoggingTestCase(LoggingTestsMixin, unittest.TestCase):
    pass


class LoggingTestCaseTests(unittest.TestCase):
    """Tests for the LoggingTestCase."""

    @classmethod
    def setUpClass(cls):
        cls.log = get_logger(__name__)

    def test_assert_not_logs_does_not_raise_with_no_logs(self):
        """Test if LoggingTestCase.assertNotLogs does not raise when no logs were emitted."""
        try:
            with LoggingTestCase.assertNotLogs(self, level=logging.DEBUG):
                pass
        except AssertionError:  # pragma: no cover
            self.fail("`self.assertNotLogs` raised an AssertionError when it should not!")

    def test_assert_not_logs_raises_correct_assertion_error_when_logs_are_emitted(self):
        """Test if LoggingTestCase.assertNotLogs raises AssertionError when logs were emitted."""
        msg_regex = (
            r"1 logs of DEBUG or higher were triggered on root:\n"
            r'<LogRecord: tests\.test_base, [\d]+, .+[/\\]tests[/\\]test_base\.py, [\d]+, "Log!">'
        )
        with (
            self.assertRaisesRegex(AssertionError, msg_regex),
            LoggingTestCase.assertNotLogs(self, level=logging.DEBUG),
        ):
            self.log.debug("Log!")

    def test_assert_not_logs_reraises_unexpected_exception_in_managed_context(self):
        """Test if LoggingTestCase.assertNotLogs reraises an unexpected exception."""
        with (
            self.assertRaises(ValueError, msg="test exception"),
            LoggingTestCase.assertNotLogs(self, level=logging.DEBUG),
        ):
            raise ValueError("test exception")

    def test_assert_not_logs_restores_old_logging_settings(self):
        """Test if LoggingTestCase.assertNotLogs reraises an unexpected exception."""
        old_handlers = self.log.handlers[:]
        old_level = self.log.level
        old_propagate = self.log.propagate

        with LoggingTestCase.assertNotLogs(self, level=logging.DEBUG):
            pass

        self.assertEqual(self.log.handlers, old_handlers)
        self.assertEqual(self.log.level, old_level)
        self.assertEqual(self.log.propagate, old_propagate)

    def test_logging_test_case_works_with_logger_instance(self):
        """Test if the LoggingTestCase captures logging for provided logger."""
        log = get_logger("new_logger")
        with self.assertRaises(AssertionError), LoggingTestCase.assertNotLogs(self, logger=log):
            log.info("Hello, this should raise an AssertionError")

    def test_logging_test_case_respects_alternative_logger(self):
        """Test if LoggingTestCase only checks the provided logger."""
        log_one = get_logger("log one")
        log_two = get_logger("log two")
        with LoggingTestCase.assertNotLogs(self, logger=log_one):
            log_two.info("Hello, this should not raise an AssertionError")

    def test_logging_test_case_respects_logging_level(self):
        """Test if LoggingTestCase does not raise for a logging level lower than provided."""
        with LoggingTestCase.assertNotLogs(self, level=logging.CRITICAL):
            self.log.info("Hello, this should raise an AssertionError")

    def test_capture_log_handler_default_initialization(self):
        """Test if the _CaptureLogHandler is initialized properly."""
        handler = _CaptureLogHandler()
        self.assertFalse(handler.records)

    def test_capture_log_handler_saves_record_on_emit(self):
        """Test if the _CaptureLogHandler saves the log record when it's emitted."""
        handler = _CaptureLogHandler()
        handler.emit("Log message")
        self.assertIn("Log message", handler.records)
