import asyncio
import logging
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import aiohttp.hdrs
from aiohttp import ClientConnectorError

from bot.utils import services
from tests.helpers import MockBot, autospec


class RequestTests(unittest.IsolatedAsyncioTestCase):
    """Test the attempt_request utility function."""

    def setUp(self) -> None:
        patcher = patch("bot.instance", new=MockBot())
        self.bot = patcher.start()
        self.addCleanup(patcher.stop)

        self.bot.http_session.request = AsyncMock()

    async def test_successful_post(self):
        """The utility makes one request, and returns the response object when successful."""
        response = MagicMock()
        self.bot.http_session.request.return_value = response
        self.bot.http_session.reset_mock()

        url = "url"
        actual_response = await services._attempt_request(url, 1)
        self.bot.http_session.request.assert_called_once_with(aiohttp.hdrs.METH_POST, url)
        self.assertEqual(response, actual_response)

    async def test_callback_called(self):
        """If callback is passed, it's called upon success, and it's value returned."""
        return_value = "Callback return"
        callback = AsyncMock(return_value=return_value)

        response = MagicMock()
        self.bot.http_session.request.return_value = response

        actual_response = await services._attempt_request("url", 1, callback=callback)
        self.assertEqual(
            return_value,
            actual_response,
            "The function was expected to return the result of the callback."
        )

        callback.assert_called_once_with(response, 1, 1)

    async def test_repeat_request(self):
        """Test that requests are repeated on failure."""
        # Use ClientConnectorError here to avoid swallowing actual errors
        responses: list[AsyncMock] = [
            AsyncMock(side_effect=ClientConnectorError(Mock(), Mock())),
            AsyncMock(side_effect=ClientConnectorError(Mock(), Mock())),
            AsyncMock(return_value="Success"),
        ]

        for attempts in range(1, len(responses) + 1):
            final_mock = responses[attempts - 1]
            expected_failure = final_mock.side_effect is not None
            final_mock.reset_mock()

            with self.subTest(attempts=attempts, expected_failure=expected_failure):
                # Call the mocks to get a coroutine, and return each coroutine in subsequent calls to `request`
                wrapped_responses = [mock.__call__() for mock in responses[0:attempts]]
                self.bot.http_session.request = Mock(side_effect=wrapped_responses)

                # Ensure we didn't swallow any exceptions
                try:
                    with self.assertLogs(services.log, logging.ERROR) as logs:
                        response = await services._attempt_request("url", attempts)
                except AssertionError:
                    # assertLogs raised an exception because no logs existed, as expected
                    pass
                else:
                    # assertLogs did not raise an exception, because it found logs
                    output = "\n\n".join(logs.output)
                    raise Exception(f"Unexpected exceptions raised during this run:\n{output}")

                self.assertEqual(None if expected_failure else "Success", response)
                self.assertEqual(attempts, self.bot.http_session.request.call_count)

    async def test_repeat_callback(self):
        """Test that `callback` is repeated with a new request if it returns None."""
        async def callback(_response, *_):
            return _response

        self.bot.http_session.request = AsyncMock(side_effect=(None, "Valid response"))
        response = await services._attempt_request("url", 2, callback=callback)

        self.assertEqual("Valid response", response)
        self.assertEqual(2, self.bot.http_session.request.call_count)

    async def test_catch_exceptions(self):
        """Test that all exceptions are caught and return None."""
        self.bot.http_session.request = AsyncMock(side_effect=Exception("Mock exception"))

        with self.assertLogs(services.log, logging.ERROR):
            response = await services._attempt_request("url", 1)
            self.assertIsNone(response)

    async def test_callback_error(self):
        """Test that callback is repeated with a new request if it raises an error."""
        async def callback(_response, *_):
            return _response()

        responses = (
            MagicMock(side_effect=Exception("Mock exception")),
            MagicMock(return_value="Valid return"),
        )
        self.bot.http_session.request = AsyncMock(side_effect=responses)

        response = await services._attempt_request("url", len(responses), callback=callback)

        self.assertEqual(len(responses), self.bot.http_session.request.call_count)

        self.assertEqual("Valid return", response, "The function did not return the correct output from the callback.")
        for request_response in responses:
            request_response.assert_called_once()


class PasteTests(unittest.IsolatedAsyncioTestCase):
    """Test the core logic of the paste service."""

    def setUp(self) -> None:
        patcher = patch("bot.instance", new=MockBot())
        self.bot = patcher.start()
        self.addCleanup(patcher.stop)

        self.bot.http_session.request = AsyncMock()

    @patch("bot.utils.services.URLs.paste_service", "https://paste_service.com/{key}")
    @autospec(services, "_attempt_request", pass_mocks=True)
    async def test_url_and_sent_contents(self, attempt_request: MagicMock):
        """Correct url was used and post was called with expected data."""
        await services.send_to_paste_service("Content")

        attempt_request.assert_called_once()
        call = attempt_request.mock_calls[0]

        args = ("https://paste_service.com/documents", services.FAILED_REQUEST_ATTEMPTS)
        self.assertEqual(args, call.args, "Request function called with incorrect arguments.")
        self.assertEqual("Content", call.kwargs["data"], "Expected data kwargs to be set to `Content`.")
        self.assertTrue(
            asyncio.iscoroutinefunction(call.kwargs["callback"]),
            "Callback was expected to be an async function."
        )

    @patch("bot.utils.services.URLs.paste_service", "https://paste_service.com/{key}")
    async def test_paste_returns_correct_url_on_success(self):
        """Url with specified extension is returned on successful requests."""
        key = "paste_key"
        test_cases = (
            (f"https://paste_service.com/{key}.txt?noredirect", "txt"),
            (f"https://paste_service.com/{key}.py", "py"),
            (f"https://paste_service.com/{key}?noredirect", ""),
        )
        self.bot.http_session.request.return_value = AsyncMock(json=AsyncMock(return_value={"key": key}))

        for expected_output, extension in test_cases:
            with self.subTest(msg=f"Send contents with extension {repr(extension)}"):
                self.assertEqual(
                    await services.send_to_paste_service("", extension=extension),
                    expected_output
                )

    @autospec(services, "_attempt_request", pass_mocks=True)
    async def test_request_repeated_on_json_errors(self, attempt_request: MagicMock):
        """If the paste service returns an error, the callback will return None to repeat the request."""
        # Get the callback which contains the logic that handles the responses
        await services.send_to_paste_service("")
        callback = attempt_request.mock_calls[0].kwargs["callback"]

        test_cases = ({"message": "error"}, {"unexpected_key": None}, {})

        for error_json in test_cases:
            with self.subTest(error_json=error_json):
                with self.assertLogs(services.log, logging.WARNING):
                    response = AsyncMock(json=AsyncMock(return_value=error_json))
                    self.assertIsNone(
                        await callback(response, Mock(), Mock()),
                        "Callback expected to return None on failure, to repeat request."
                    )
