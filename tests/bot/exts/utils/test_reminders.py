import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bot.exts.utils.reminders import Reminders
from tests.helpers import MockBot


class RemindersCogLoadTests(unittest.IsolatedAsyncioTestCase):
    """ Tests startup behaviour of the Reminders cog. """

    def setUp(self):
        self.bot = MockBot()
        self.bot.wait_until_guild_available = AsyncMock()
        self.cog = Reminders(self.bot)

        self.cog._alert_mods_if_loading_failed = AsyncMock()
        self.cog.ensure_valid_reminder = MagicMock(return_value=(False, None))
        self.cog.schedule_reminder = MagicMock()
        self.cog._alert_mods_if_loading_failed = AsyncMock()

        self.bot.api_client = MagicMock()
        self.bot.api_client.get = AsyncMock()

    @patch("bot.exts.utils.reminders.asyncio.sleep", new_callable=AsyncMock)
    async def test_reminders_cog_loads(self, sleep_mock):
        """ Tests if the Reminders cog loads without error if the GET requests works. """
        self.bot.api_client.get.return_value = []
        try:
            await self.cog.cog_load()
        except Exception as e:
            self.fail(f"Reminders cog failed to load with exception: {e}")
