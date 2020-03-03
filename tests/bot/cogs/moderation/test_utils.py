import unittest
from unittest.mock import AsyncMock

from tests.helpers import MockBot, MockContext, MockMember


class ModerationUtilsTests(unittest.IsolatedAsyncioTestCase):
    """Tests Moderation utils."""

    def setUp(self):
        self.bot = MockBot()
        self.member = MockMember(id=1234)
        self.ctx = MockContext(bot=self.bot, author=self.member)
        self.bot.api_client.get = AsyncMock()
