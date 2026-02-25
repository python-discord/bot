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
