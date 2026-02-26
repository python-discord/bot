import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bot.constants import URLs
from bot.exts.utils.reminders import Reminders
from tests.helpers import MockBot

MAX_RETRY_ATTEMPTS = URLs.connect_max_retries


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

    async def test_reminders_cog_loads_correctly(self):
        """ Tests if the Reminders cog loads without error if the GET requests works. """
        self.bot.api_client.get.return_value = []
        try:
            with patch("bot.exts.utils.reminders.asyncio.sleep", new_callable=AsyncMock):
                await self.cog.cog_load()
        except Exception as e:
            self.fail(f"Reminders cog failed to load with exception: {e}")

    async def test_reminders_cog_load_retries_after_initial_exception(self):
        """ Tests if the Reminders cog loads after retrying on initial exception. """
        self.bot.api_client.get.side_effect = [Exception("fail 1"), Exception("fail 2"), []]
        try:
            with patch("bot.exts.utils.reminders.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await self.cog.cog_load()
        except Exception as e:
            self.fail(f"Reminders cog failed to load after retrying with exception: {e}")
        self.assertEqual(mock_sleep.await_count, 2)
        self.bot.api_client.get.assert_called()

    async def test_reminders_cog_load_fails_after_max_retries(self):
        """ Tests if the Reminders cog fails to load after max retries. """
        self.bot.api_client.get.side_effect = RuntimeError("fail")
        with patch("bot.exts.utils.reminders.asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
             self.assertRaises(RuntimeError):
            await self.cog.cog_load()

        # Should have retried MAX_RETRY_ATTEMPTS - 1 times before failing
        self.assertEqual(mock_sleep.await_count, MAX_RETRY_ATTEMPTS - 1)
        self.bot.api_client.get.assert_called()
        self.cog._alert_mods_if_loading_failed.assert_called_once()
