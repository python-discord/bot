import unittest
from unittest.mock import AsyncMock, MagicMock, patch

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

    async def test_cog_load_when_filter_list_fetch_fails(self):
        """`cog_load` should currently raise if loading filter lists from the API fails."""
        self.bot.api_client.get.side_effect = OSError("Simulated site/API outage during cog_load")

        with self.assertRaises(RuntimeError):
            await self.cog.cog_load()

        self.bot.wait_until_guild_available.assert_awaited_once()
        self.bot.api_client.get.assert_awaited_once_with("bot/filter/filter_lists")

        # Startup should stop before later steps.
        self.cog._fetch_or_generate_filtering_webhook.assert_not_awaited()
        self.cog.schedule_offending_messages_deletion.assert_not_awaited()
        self.mock_weekly_task_start.assert_not_called()

    async def test_cog_load_completes_when_filter_list_fetch_succeeds(self):
        """`cog_load` should continue startup when the API returns filter lists successfully."""
        self.bot.api_client.get.return_value = []

        await self.cog.cog_load()

        self.bot.wait_until_guild_available.assert_awaited_once()
        self.bot.api_client.get.assert_awaited_once_with("bot/filter/filter_lists")
        self.cog._fetch_or_generate_filtering_webhook.assert_awaited_once()
        self.cog.collect_loaded_types.assert_called_once_with(None)
        self.cog.schedule_offending_messages_deletion.assert_awaited_once()
        self.mock_weekly_task_start.assert_called_once()
