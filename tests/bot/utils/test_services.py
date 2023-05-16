import logging
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from aiohttp import ClientConnectorError

from bot.utils.services import (
    FAILED_REQUEST_ATTEMPTS, MAX_PASTE_LENGTH, PasteTooLongError, PasteUploadError, send_to_paste_service
)
from tests.helpers import MockBot


class PasteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        patcher = patch("bot.instance", new=MockBot())
        self.bot = patcher.start()
        self.addCleanup(patcher.stop)

    @patch("bot.utils.services.URLs.paste_service", "https://paste_service.com/{key}")
    async def test_url_and_sent_contents(self):
        """Correct url was used and post was called with expected data."""
        response = MagicMock(
            json=AsyncMock(return_value={"key": ""})
        )
        self.bot.http_session.post.return_value.__aenter__.return_value = response
        self.bot.http_session.post.reset_mock()
        await send_to_paste_service("Content")
        self.bot.http_session.post.assert_called_once_with("https://paste_service.com/documents", data="Content")

    @patch("bot.utils.services.URLs.paste_service", "https://paste_service.com/{key}")
    async def test_paste_returns_correct_url_on_success(self):
        """Url with specified extension is returned on successful requests."""
        key = "paste_key"
        test_cases = (
            (f"https://paste_service.com/{key}.txt?noredirect", "txt"),
            (f"https://paste_service.com/{key}.py", "py"),
            (f"https://paste_service.com/{key}?noredirect", ""),
        )
        response = MagicMock(
            json=AsyncMock(return_value={"key": key})
        )
        self.bot.http_session.post.return_value.__aenter__.return_value = response

        for expected_output, extension in test_cases:
            with self.subTest(msg=f"Send contents with extension {extension!r}"):
                self.assertEqual(
                    await send_to_paste_service("", extension=extension),
                    expected_output
                )

    async def test_request_repeated_on_json_errors(self):
        """Json with error message and invalid json are handled as errors and requests repeated."""
        test_cases = ({"message": "error"}, {"unexpected_key": None}, {})
        self.bot.http_session.post.return_value.__aenter__.return_value = response = MagicMock()
        self.bot.http_session.post.reset_mock()

        for error_json in test_cases:
            with self.subTest(error_json=error_json):
                response.json = AsyncMock(return_value=error_json)
                with self.assertRaises(PasteUploadError):
                    await send_to_paste_service("")
                self.assertEqual(self.bot.http_session.post.call_count, FAILED_REQUEST_ATTEMPTS)

            self.bot.http_session.post.reset_mock()

    async def test_request_repeated_on_connection_errors(self):
        """Requests are repeated in the case of connection errors."""
        self.bot.http_session.post = MagicMock(side_effect=ClientConnectorError(Mock(), Mock()))
        with self.assertRaises(PasteUploadError):
            await send_to_paste_service("")
        self.assertEqual(self.bot.http_session.post.call_count, FAILED_REQUEST_ATTEMPTS)

    async def test_general_error_handled_and_request_repeated(self):
        """All `Exception`s are handled, logged and request repeated."""
        self.bot.http_session.post = MagicMock(side_effect=Exception)
        with self.assertRaises(PasteUploadError):
            await send_to_paste_service("")
        self.assertEqual(self.bot.http_session.post.call_count, FAILED_REQUEST_ATTEMPTS)
        self.assertLogs("bot.utils", logging.ERROR)

    async def test_raises_error_on_too_long_input(self):
        """Ensure PasteTooLongError is raised if `contents` is longer than `MAX_PASTE_LENGTH`."""
        contents = "a" * (MAX_PASTE_LENGTH + 1)
        with self.assertRaises(PasteTooLongError):
            await send_to_paste_service(contents)

    async def test_raises_on_too_large_max_length(self):
        """Ensure ValueError is raised if `max_length` passed is greater than `MAX_PASTE_LENGTH`."""
        with self.assertRaises(ValueError):
            await send_to_paste_service("Hello World!", max_length=MAX_PASTE_LENGTH + 1)
