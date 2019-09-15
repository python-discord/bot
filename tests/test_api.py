import logging
from unittest.mock import MagicMock, patch

import pytest

from bot import api
from tests.helpers import async_test


def test_loop_is_not_running_by_default():
    assert not api.loop_is_running()


@async_test
async def test_loop_is_running_in_async_test():
    assert api.loop_is_running()


@pytest.fixture()
def error_api_response():
    response = MagicMock()
    response.status = 999
    return response


@pytest.fixture()
def api_log_handler():
    return api.APILoggingHandler(None)


@pytest.fixture()
def debug_log_record():
    return logging.LogRecord(
        name='my.logger', level=logging.DEBUG,
        pathname='my/logger.py', lineno=666,
        msg="Lemon wins", args=(),
        exc_info=None
    )


def test_response_code_error_default_initialization(error_api_response):
    error = api.ResponseCodeError(response=error_api_response)
    assert error.status is error_api_response.status
    assert not error.response_json
    assert not error.response_text
    assert error.response is error_api_response


def test_response_code_error_default_representation(error_api_response):
    error = api.ResponseCodeError(response=error_api_response)
    assert str(error) == f"Status: {error_api_response.status} Response: "


def test_response_code_error_representation_with_nonempty_response_json(error_api_response):
    error = api.ResponseCodeError(
        response=error_api_response,
        response_json={'hello': 'world'}
    )
    assert str(error) == f"Status: {error_api_response.status} Response: {{'hello': 'world'}}"


def test_response_code_error_representation_with_nonempty_response_text(error_api_response):
    error = api.ResponseCodeError(
        response=error_api_response,
        response_text='Lemon will eat your soul'
    )
    assert str(error) == f"Status: {error_api_response.status} Response: Lemon will eat your soul"


@patch('bot.api.APILoggingHandler.ship_off')
def test_emit_appends_to_queue_with_stopped_event_loop(
    ship_off_patch, api_log_handler, debug_log_record
):
    # This is a coroutine so returns something we should await,
    # but asyncio complains about that. To ease testing, we patch
    # `ship_off` to just return a regular value instead.
    ship_off_patch.return_value = 42
    api_log_handler.emit(debug_log_record)

    assert api_log_handler.queue == [42]


def test_emit_ignores_less_than_debug(debug_log_record, api_log_handler):
    debug_log_record.levelno = logging.DEBUG - 5
    api_log_handler.emit(debug_log_record)
    assert not api_log_handler.queue


def test_schedule_queued_tasks_for_empty_queue(api_log_handler, caplog):
    api_log_handler.schedule_queued_tasks()
    # Logs when tasks are scheduled
    assert not caplog.records


@patch('asyncio.create_task')
def test_schedule_queued_tasks_for_nonempty_queue(create_task_patch, api_log_handler, caplog):
    api_log_handler.queue = [555]
    api_log_handler.schedule_queued_tasks()
    assert not api_log_handler.queue
    create_task_patch.assert_called_once_with(555)

    [record] = caplog.records
    assert record.message == "Scheduled 1 pending logging tasks."
    assert record.levelno == logging.DEBUG
    assert record.name == 'bot.api'
    assert record.__dict__['via_handler']
