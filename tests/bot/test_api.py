import logging
import unittest
from unittest.mock import MagicMock, patch

from bot import api
from tests.base import LoggingTestCase
from tests.helpers import async_test


class APIClientTests(unittest.TestCase):
    """Tests for the bot's API client."""

    @classmethod
    def setUpClass(cls):
        """Sets up the shared fixtures for the tests."""
        cls.error_api_response = MagicMock()
        cls.error_api_response.status = 999

    def test_loop_is_not_running_by_default(self):
        """The event loop should not be running by default."""
        self.assertFalse(api.loop_is_running())

    @async_test
    async def test_loop_is_running_in_async_context(self):
        """The event loop should be running in an async context."""
        self.assertTrue(api.loop_is_running())

    def test_response_code_error_default_initialization(self):
        """Test the default initialization of `ResponseCodeError` without `text` or `json`"""
        error = api.ResponseCodeError(response=self.error_api_response)

        self.assertIs(error.status, self.error_api_response.status)
        self.assertEqual(error.response_json, {})
        self.assertEqual(error.response_text, "")
        self.assertIs(error.response, self.error_api_response)

    def test_responde_code_error_string_representation_default_initialization(self):
        """Test the string representation of `ResponseCodeError` initialized without text or json."""
        error = api.ResponseCodeError(response=self.error_api_response)
        self.assertEqual(str(error), f"Status: {self.error_api_response.status} Response: ")

    def test_response_code_error_initialization_with_json(self):
        """Test the initialization of `ResponseCodeError` with json."""
        json_data = {'hello': 'world'}
        error = api.ResponseCodeError(
            response=self.error_api_response,
            response_json=json_data,
        )
        self.assertEqual(error.response_json, json_data)
        self.assertEqual(error.response_text, "")

    def test_response_code_error_string_representation_with_nonempty_response_json(self):
        """Test the string representation of `ResponseCodeError` initialized with json."""
        json_data = {'hello': 'world'}
        error = api.ResponseCodeError(
            response=self.error_api_response,
            response_json=json_data
        )
        self.assertEqual(str(error), f"Status: {self.error_api_response.status} Response: {json_data}")

    def test_response_code_error_initialization_with_text(self):
        """Test the initialization of `ResponseCodeError` with text."""
        text_data = 'Lemon will eat your soul'
        error = api.ResponseCodeError(
            response=self.error_api_response,
            response_text=text_data,
        )
        self.assertEqual(error.response_text, text_data)
        self.assertEqual(error.response_json, {})

    def test_response_code_error_string_representation_with_nonempty_response_text(self):
        """Test the string representation of `ResponseCodeError` initialized with text."""
        text_data = 'Lemon will eat your soul'
        error = api.ResponseCodeError(
            response=self.error_api_response,
            response_text=text_data
        )
        self.assertEqual(str(error), f"Status: {self.error_api_response.status} Response: {text_data}")


class LoggingHandlerTests(LoggingTestCase):
    """Tests the bot's API Log Handler."""

    @classmethod
    def setUpClass(cls):
        cls.debug_log_record = logging.LogRecord(
            name='my.logger', level=logging.DEBUG,
            pathname='my/logger.py', lineno=666,
            msg="Lemon wins", args=(),
            exc_info=None
        )

        cls.trace_log_record = logging.LogRecord(
            name='my.logger', level=logging.TRACE,
            pathname='my/logger.py', lineno=666,
            msg="This will not be logged", args=(),
            exc_info=None
        )

    def setUp(self):
        self.log_handler = api.APILoggingHandler(None)

    def test_emit_appends_to_queue_with_stopped_event_loop(self):
        """Test if `APILoggingHandler.emit` appends to queue when the event loop is not running."""
        with patch("bot.api.APILoggingHandler.ship_off") as ship_off:
            # Patch `ship_off` to ease testing against the return value of this coroutine.
            ship_off.return_value = 42
            self.log_handler.emit(self.debug_log_record)

        self.assertListEqual(self.log_handler.queue, [42])

    def test_emit_ignores_less_than_debug(self):
        """`APILoggingHandler.emit` should not queue logs with a log level lower than DEBUG."""
        self.log_handler.emit(self.trace_log_record)
        self.assertListEqual(self.log_handler.queue, [])

    def test_schedule_queued_tasks_for_empty_queue(self):
        """`APILoggingHandler` should not schedule anything when the queue is empty."""
        with self.assertNotLogs(level=logging.DEBUG):
            self.log_handler.schedule_queued_tasks()

    def test_schedule_queued_tasks_for_nonempty_queue(self):
        """`APILoggingHandler` should schedule logs when the queue is not empty."""
        with self.assertLogs(level=logging.DEBUG) as logs, patch('asyncio.create_task') as create_task:
            self.log_handler.queue = [555]
            self.log_handler.schedule_queued_tasks()
            self.assertListEqual(self.log_handler.queue, [])
            create_task.assert_called_once_with(555)

            [record] = logs.records
            self.assertEqual(record.message, "Scheduled 1 pending logging tasks.")
            self.assertEqual(record.levelno, logging.DEBUG)
            self.assertEqual(record.name, 'bot.api')
            self.assertIn('via_handler', record.__dict__)
