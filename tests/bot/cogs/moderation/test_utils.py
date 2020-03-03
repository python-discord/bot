import unittest
from unittest.mock import AsyncMock

from bot.cogs.moderation.utils import has_active_infraction
from tests.helpers import MockBot, MockContext, MockMember


class ModerationUtilsTests(unittest.IsolatedAsyncioTestCase):
    """Tests Moderation utils."""

    def setUp(self):
        self.bot = MockBot()
        self.member = MockMember(id=1234)
        self.ctx = MockContext(bot=self.bot, author=self.member)
        self.bot.api_client.get = AsyncMock()

    async def test_user_has_active_infraction_true(self):
        """Test does `has_active_infraction` return that user have active infraction."""
        self.bot.api_client.get.return_value = [{
            "id": 1,
            "inserted_at": "2018-11-22T07:24:06.132307Z",
            "expires_at": "5018-11-20T15:52:00Z",
            "active": True,
            "user": 1234,
            "actor": 1234,
            "type": "ban",
            "reason": "Test",
            "hidden": False
        }]
        self.assertTrue(await has_active_infraction(self.ctx, self.member, "ban"), "User should have active infraction")

    async def test_user_has_active_infraction_false(self):
        """Test does `has_active_infraction` return that user don't have active infractions."""
        self.bot.api_client.get.return_value = []
        self.assertFalse(
            await has_active_infraction(self.ctx, self.member, "ban"),
            "User shouldn't have active infraction"
        )
