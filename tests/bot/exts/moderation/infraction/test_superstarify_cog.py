import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bot.exts.moderation.infraction.superstarify import Superstarify
from tests.helpers import MockBot


class TestSuperstarify(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.bot = MockBot()

        self.cog = Superstarify(self.bot)

        self.bot.api_client = MagicMock()
        self.bot.api_client.get = AsyncMock()

        self.cog._alert_mods_if_loading_failed = AsyncMock()
        self.cog._check_error_is_retriable = MagicMock(return_value=True)

    async def test_fetch_from_api_success(self):
        """API succeeds on first attempt."""
        expected = [{"id": 1}]
        self.bot.api_client.get.return_value = expected

        result = await self.cog._fetch_with_retries(
            params={"user__id": "123"}
        )
        self.assertEqual(result, expected)

        self.bot.api_client.get.assert_awaited_once_with(
            "bot/infractions",
            params={"user__id": "123"},
        )
        self.cog._alert_mods_if_loading_failed.assert_not_called()

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_fetch_retries_then_succeeds(self, _):
        self.bot.api_client.get.side_effect = [
            OSError("temporary failure"),
            [{"id": 42}],
        ]

        result = await self.cog._fetch_with_retries(
            params={"user__id": "123"}
        )

        self.assertEqual(result, [{"id": 42}])
        self.assertEqual(self.bot.api_client.get.await_count, 2)

        self.cog._alert_mods_if_loading_failed.assert_not_called()

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_fetch_fails_after_max_retries(self, _):
        error = OSError("API down")

        self.bot.api_client.get.side_effect = error

        with self.assertRaises(OSError):
            await self.cog._fetch_with_retries(
                retries=3,
                params={"user__id": "123"},
            )

        self.assertEqual(self.bot.api_client.get.await_count, 3)

        self.cog._alert_mods_if_loading_failed.assert_awaited_once_with(error)

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_non_retriable_error_stops_immediately(self, _):
        error = ValueError("bad request")

        self.bot.api_client.get.side_effect = error
        self.cog._check_error_is_retriable.return_value = False

        with self.assertRaises(ValueError):
            await self.cog._fetch_with_retries()

        # only one attempt
        self.bot.api_client.get.assert_awaited_once()

        self.cog._alert_mods_if_loading_failed.assert_awaited_once()

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_member_update_recovers_from_api_failure(self, _):
        before = MagicMock(display_name="Old", id=123)
        after = MagicMock(display_name="New", id=123)
        after.edit = AsyncMock()

        self.bot.api_client.get.side_effect = [
            OSError(),
            [{"id": 42}],
        ]

        self.cog.get_nick = MagicMock(return_value="Taylor Swift")

        with patch(
            "bot.exts.moderation.infraction._utils.notify_infraction",
            new=AsyncMock(return_value=True),
        ):
            await self.cog.on_member_update(before, after)

        after.edit.assert_awaited_once()

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_alert_triggered_after_total_failure(self, _):
        self.bot.api_client.get.side_effect = OSError("down")

        with self.assertRaises(OSError):
            await self.cog._fetch_with_retries(retries=3)

        self.cog._alert_mods_if_loading_failed.assert_awaited_once()
