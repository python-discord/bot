import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from pydis_core.site_api import ResponseCodeError

from bot.exts.filtering.filtering import Filtering


class FilteringCogLoadTests(unittest.IsolatedAsyncioTestCase):
    """Test startup behavior of the Filtering cog (`cog_load`)."""

    def setUp(self) -> None:
        """Set up a Filtering cog with a mocked bot and stubbed startup dependencies."""
        self.bot = MagicMock()
        self.bot.wait_until_guild_available = AsyncMock()

        self.bot.api_client = MagicMock()
        self.bot.api_client.get = AsyncMock()

        self.cog = Filtering(self.bot)

        # Stub internals that are not relevant to this unit test.
        self.cog.collect_loaded_types = MagicMock()
        self.cog.schedule_offending_messages_deletion = AsyncMock()
        self.cog._fetch_or_generate_filtering_webhook = AsyncMock(return_value=MagicMock())

        # `weekly_auto_infraction_report_task` is a discord task loop; patch its start method.
        self.start_patcher = patch.object(self.cog.weekly_auto_infraction_report_task, "start")
        self.mock_weekly_task_start = self.start_patcher.start()
        self.addCleanup(self.start_patcher.stop)

    async def test_cog_load_retries_then_succeeds(self):
        """`cog_load` should retry temporary failures and complete startup after a successful fetch."""
        self.bot.api_client.get.side_effect = [
            OSError("temporary outage"),
            TimeoutError("temporary timeout"),
            [],
        ]
        self.cog._alert_mods_filter_load_failure = AsyncMock()

        with patch("bot.exts.filtering.filtering.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await self.cog.cog_load()

        self.bot.wait_until_guild_available.assert_awaited_once()
        self.assertEqual(self.bot.api_client.get.await_count, 3)
        self.bot.api_client.get.assert_awaited_with("bot/filter/filter_lists")
        self.assertEqual(mock_sleep.await_count, 2)
        self.cog._alert_mods_filter_load_failure.assert_not_awaited()
        self.cog._fetch_or_generate_filtering_webhook.assert_awaited_once()
        self.cog.collect_loaded_types.assert_called_once_with(None)
        self.cog.schedule_offending_messages_deletion.assert_awaited_once()
        self.mock_weekly_task_start.assert_called_once()

    async def test_retries_three_times_fails_and_alerts(self):
        """`cog_load` should alert and re-raise when all retry attempts fail."""
        self.bot.api_client.get.side_effect = OSError("Simulated site/API outage during cog_load")
        self.cog._alert_mods_filter_load_failure = AsyncMock()

        with (
            patch("bot.exts.filtering.filtering.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            self.assertRaises(OSError),
        ):
            await self.cog.cog_load()

        self.bot.wait_until_guild_available.assert_awaited_once()
        self.assertEqual(self.bot.api_client.get.await_count, 3)
        self.bot.api_client.get.assert_awaited_with("bot/filter/filter_lists")
        self.assertEqual(mock_sleep.await_count, 2)
        self.cog._alert_mods_filter_load_failure.assert_awaited_once()

        error, attempts = self.cog._alert_mods_filter_load_failure.await_args.args
        self.assertIsInstance(error, OSError)
        self.assertEqual(attempts, 3)

        # Startup should stop before later steps.
        self.cog._fetch_or_generate_filtering_webhook.assert_not_awaited()
        self.cog.schedule_offending_messages_deletion.assert_not_awaited()
        self.mock_weekly_task_start.assert_not_called()

    def test_retryable_filter_load_error(self):
        """`_retryable_filter_load_error` should classify temporary failures as retryable."""
        test_cases = (
            (ResponseCodeError(MagicMock(status=429)), True),
            (ResponseCodeError(MagicMock(status=500)), True),
            (ResponseCodeError(MagicMock(status=503)), True),
            (ResponseCodeError(MagicMock(status=400)), False),
            (ResponseCodeError(MagicMock(status=404)), False),
            (TimeoutError("timeout"), True),
            (OSError("os error"), True),
            (AttributeError("attr"), False),
            (ValueError("value"), False),
        )

        for error, expected_retryable in test_cases:
            with self.subTest(error=error):
                self.assertEqual(self.cog._retryable_filter_load_error(error), expected_retryable)
