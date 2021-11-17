import asyncio
import datetime
import json
import logging
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import aiohttp.hdrs
from aiohttp import ClientConnectorError
from async_rediscache import RedisSession

from bot import constants
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


@autospec(services, "_attempt_request", pass_mocks=True)
class UnfurlTests(unittest.IsolatedAsyncioTestCase):
    """Test the URL unfurling utility."""

    async def asyncSetUp(self) -> None:
        """Instantiate a redis session for every test, and clean it up afterwards."""
        redis_session = RedisSession(use_fakeredis=True)
        await redis_session.connect()
        self.addAsyncCleanup(redis_session.close)

    class ResponseMock(MagicMock):
        """Utility class which can be used to mock responses from the worker."""
        class _StatusException(Exception):
            pass

        def __init__(self, status: int, content: dict, **kwargs):
            super().__init__(status=status, content=content, **kwargs)
            self.status = status

        async def json(self):
            return self.content

        def raise_for_status(self):
            if self.status >= 400:
                raise self._StatusException("Exception raised from response mock.")

    async def test_simple_redirect(self, attempt_request: AsyncMock):
        """Test a successful, short redirect."""
        attempt_request.return_value = UnfurlTests.ResponseMock(200, {
            "destination": "dest url",
            "depth": 1
        })

        expected_result = ("dest url", 1, None)

        result = await services.unfurl_url("url", max_continues=0, use_cache=False)
        self.assertEqual(expected_result, (result.destination, result.depth, result.error))

        cached = await services._get_url_from_cache("url")
        self.assertEqual(
            expected_result,
            (cached.destination, cached.depth, cached.error),
            "Incorrect result saved to cache."
        )

    async def test_continue(self, attempt_request: AsyncMock):
        """Test that the utility continues if we reach max-depth."""
        requests = (
            (416, {"error": "", "depth": 5, "final": "final url", "next": "next url"}),
            (200, {"destination": "dest url", "depth": 3})
        )
        expected_results = ("dest url", sum(i[1]["depth"] for i in requests) + 1, None)

        attempt_request.side_effect = [UnfurlTests.ResponseMock(*data) for data in requests]
        result = await services.unfurl_url("url", max_continues=1, use_cache=False)

        self.assertEqual(expected_results, (result.destination, result.depth, result.error))

        self.assertEqual(2, attempt_request.call_count, "Expected the request function to be called twice.")
        attempt_request.assert_has_calls(any_order=False, calls=[
            unittest.mock.call(constants.URLs.unfurl_worker, 3, json={"url": "url"}, raise_for_status=False),
            unittest.mock.call(constants.URLs.unfurl_worker, 3, json={"url": "next url"}, raise_for_status=False),
        ])

        cached = await services._get_url_from_cache("url")
        self.assertEqual(
            expected_results,
            (cached.destination, cached.depth, cached.error),
            "Incorrect result saved to cache for the main URL."
        )

        self.assertIsNone(
            await services._get_url_from_cache("next url"),
            "Should not write intermediary url to cache."
        )

    async def test_max_continues(self, attempt_request: AsyncMock):
        """Test that we fail if we reach the maximum number of allowed continues."""
        data = {"error": "error message", "depth": 5, "final": "final url", "next": "next url"}
        attempt_request.return_value = UnfurlTests.ResponseMock(416, data)

        result = await services.unfurl_url("url", max_continues=0, use_cache=False)
        self.assertEqual(
            services._UnfurlReturn(data["next"], data["depth"], data["error"]),
            result
        )

        self.assertEqual(1, attempt_request.call_count)
        self.assertIsNone(await services._get_url_from_cache("url"), "Should not write to cache on failure.")

    async def test_request_failure(self, attempt_request: AsyncMock):
        """
        Return None if the request fails to connect.

        This is different from a non-200 response status.
        """
        attempt_request.return_value = None
        self.assertIsNone(await services.unfurl_url("url", use_cache=False))
        self.assertIsNone(await services._get_url_from_cache("url"), "Should not write to cache on failure.")

    async def test_400_response(self, attempt_request: AsyncMock):
        """Test the handling of a 400 response status."""
        attempt_request.return_value = UnfurlTests.ResponseMock(400, {"error": "error message"})
        self.assertEqual(
            services._UnfurlReturn(error="error message"),
            await services.unfurl_url("url", use_cache=False),
            "Expected the return value to only have an error message."
        )

        self.assertIsNone(await services._get_url_from_cache("url"), "Should not write to cache on failure.")

    async def test_418_response(self, attempt_request: AsyncMock):
        """Test the handling of a 418 response status."""
        attempt_request.return_value = UnfurlTests.ResponseMock(418, {
            "error": "error message",
            "depth": 1,
            "final": "final url"
        })

        self.assertEqual(
            services._UnfurlReturn("final url", 1, "error message"),
            await services.unfurl_url("url", use_cache=False),
            "Expected the return value to only have an error message."
        )

        self.assertIsNone(await services._get_url_from_cache("url"), "Should not write to cache on failure.")

    async def test_unexpected_response(self, attempt_request: AsyncMock):
        """Test that an unexpected status code raises an error."""
        attempt_request.return_value = UnfurlTests.ResponseMock(500, {})
        with self.assertRaises(UnfurlTests.ResponseMock._StatusException):
            await services.unfurl_url("url")

    async def test_cache_hit(self, attempt_request: AsyncMock):
        """Test that the cache is used if possible."""
        data = {
            "destination": "",
            "depth": 1,
            "expiry": (datetime.datetime.utcnow() + datetime.timedelta(hours=1)).isoformat()
        }
        await services.UNFURL_CACHE.set("url", json.dumps(data))
        result = await services.unfurl_url("url", use_cache=True)

        self.assertEqual(("", 1, None), (result.destination, result.depth, result.error))
        attempt_request.assert_not_called()

    async def test_cache_expiry(self, _):
        """Test that expired entries aren't returned by the cache."""
        data = {
            "destination": "",
            "depth": 1,
        }

        now = datetime.datetime.utcnow()
        expired_hit = (now - datetime.timedelta(minutes=10)).isoformat()  # 10 minutes ago
        unexpired_hit = (now + datetime.timedelta(minutes=10)).isoformat()  # 10 minutes from now

        with self.subTest("Expired cache entry"):
            data["expiry"] = expired_hit
            await services.UNFURL_CACHE.set("url", json.dumps(data))
            self.assertIsNone(await services._get_url_from_cache("url"))

        with self.subTest("Unexpired cache entry"):
            data["expiry"] = unexpired_hit
            await services.UNFURL_CACHE.set("url", json.dumps(data))
            self.assertIsNotNone(await services._get_url_from_cache("url"))
