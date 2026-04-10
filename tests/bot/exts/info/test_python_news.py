import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from pydis_core.site_api import ResponseCodeError

from bot.constants import URLs
from bot.exts.info.python_news import PythonNews


class PythonNewsCogLoadTests(unittest.IsolatedAsyncioTestCase):
    """Test startup behavior of the PythonNews cog (`cog_load`)."""

    def setUp(self) -> None:
        """Set up a PythonNews cog with a mocked bot and stubbed startup dependencies."""
        self.bot = MagicMock()
        self.bot.wait_until_guild_available = AsyncMock()

        self.bot.api_client = MagicMock()
        self.bot.api_client.get = AsyncMock()
        self.bot.api_client.post = AsyncMock()

        # Required by `fetch_new_media` later, but not used in these tests.
        self.bot.http_session = MagicMock()

        self.cog = PythonNews(self.bot)

        # Stub out task-loop start, so it doesn't actually schedule anything.
        self.start_patcher = patch.object(self.cog.fetch_new_media, "start")
        self.mock_fetch_new_media_start = self.start_patcher.start()
        self.addCleanup(self.start_patcher.stop)

    async def test_cog_load_retries_then_succeeds(self):
        """`cog_load` should retry temporary failures and complete startup after a successful fetch."""
        # First two attempts fail with retryable errors, third succeeds.
        self.bot.api_client.get.side_effect = [
            OSError("temporary outage"),
            TimeoutError("temporary timeout"),
            [
                {"name": "pep", "seen_items": ["1", "2"]},
            ],
        ]

        # Ensure no missing mailing lists need creating in this test.
        with (
            patch("bot.exts.info.python_news.constants.PythonNews.mail_lists", new=()),
            patch("bot.exts.info.python_news.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await self.cog.cog_load()

        self.assertEqual(self.bot.api_client.get.await_count, 3)
        self.bot.api_client.get.assert_awaited_with("bot/mailing-lists")

        # Sleep should have been awaited for the two failed attempts.
        self.assertEqual(mock_sleep.await_count, 2)

        # Task should start after successful load.
        self.mock_fetch_new_media_start.assert_called_once()

        # State should be populated.
        self.assertIn("pep", self.cog.seen_items)
        self.assertEqual(self.cog.seen_items["pep"], {"1", "2"})

        # No posts should happen because no missing lists.
        self.bot.api_client.post.assert_not_awaited()

    async def test_retries_max_times_fails_and_reraises(self):
        """`cog_load` should re-raise when all retry attempts fail."""
        self.bot.api_client.get.side_effect = OSError("Simulated site/API outage during cog_load")

        with (
            patch("bot.exts.info.python_news.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            self.assertRaises(OSError),
        ):
            await self.cog.cog_load()

        # Should try exactly MAX_ATTEMPTS times.

        self.assertEqual(self.bot.api_client.get.await_count, URLs.connect_max_retries)
        self.bot.api_client.get.assert_awaited_with("bot/mailing-lists")

        # Sleeps happen between attempts, so MAX_ATTEMPTS - 1 times.
        self.assertEqual(mock_sleep.await_count, URLs.connect_max_retries - 1)

        # Task should never start if load fails.
        self.mock_fetch_new_media_start.assert_not_called()

    async def test_cog_load_does_not_retry_non_retryable_error(self):
        """`cog_load` should not retry when the error is non-retryable."""
        # 404 should be considered non-retryable by your predicate.
        self.bot.api_client.get.side_effect = ResponseCodeError(MagicMock(status=404))

        with (
            patch("bot.exts.info.python_news.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            self.assertRaises(ResponseCodeError),
        ):
            await self.cog.cog_load()

        self.assertEqual(self.bot.api_client.get.await_count, 1)
        self.assertEqual(mock_sleep.await_count, 0)
        self.mock_fetch_new_media_start.assert_not_called()
