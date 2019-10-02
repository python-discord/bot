import logging
import unittest
import unittest.mock


from tests.base import LoggingTestCase


class LoggingTestCaseTests(unittest.TestCase):
    """Tests for the LoggingTestCase."""

    @classmethod
    def setUpClass(cls):
        cls.log = logging.getLogger(__name__)

    def test_assert_not_logs_does_not_raise_with_no_logs(self):
        """Test if LoggingTestCase.assertNotLogs does not raise when no logs were emitted."""
        try:
            with LoggingTestCase.assertNotLogs(self, level=logging.DEBUG):
                pass
        except AssertionError:
            self.fail("`self.assertNotLogs` raised an AssertionError when it should not!")

    @unittest.mock.patch("tests.base.LoggingTestCase.assertNotLogs")
    def test_the_test_function_assert_not_logs_does_not_raise_with_no_logs(self, assertNotLogs):
        """Test if test_assert_not_logs_does_not_raise_with_no_logs captures exception correctly."""
        assertNotLogs.return_value = iter([None])
        assertNotLogs.side_effect = AssertionError

        message = "`self.assertNotLogs` raised an AssertionError when it should not!"
        with self.assertRaises(AssertionError, msg=message):
            self.test_assert_not_logs_does_not_raise_with_no_logs()

    def test_assert_not_logs_raises_correct_assertion_error_when_logs_are_emitted(self):
        """Test if LoggingTestCase.assertNotLogs raises AssertionError when logs were emitted."""
        msg_regex = (
            r"1 logs of DEBUG or higher were triggered on root:\n"
            r'<LogRecord: tests\.test_base, [\d]+, .+/tests/test_base\.py, [\d]+, "Log!">'
        )
        with self.assertRaisesRegex(AssertionError, msg_regex):
            with LoggingTestCase.assertNotLogs(self, level=logging.DEBUG):
                self.log.debug("Log!")

    def test_assert_not_logs_reraises_unexpected_exception_in_managed_context(self):
        """Test if LoggingTestCase.assertNotLogs reraises an unexpected exception."""
        with self.assertRaises(ValueError, msg="test exception"):
            with LoggingTestCase.assertNotLogs(self, level=logging.DEBUG):
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
