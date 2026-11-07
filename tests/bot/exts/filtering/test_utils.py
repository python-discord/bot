import unittest
from unittest.mock import AsyncMock, MagicMock

from bot.exts.filtering._utils import FakeContext


class FakeContextTests(unittest.IsolatedAsyncioTestCase):
    """Tests for the context-like object passed to hybrid commands invoked outside of Discord."""

    def setUp(self):
        self.channel = MagicMock()
        self.channel.send = AsyncMock()
        self.ctx = FakeContext(MagicMock(), self.channel, MagicMock(), bot=MagicMock(), guild=MagicMock())

    async def test_has_no_interaction(self):
        """Commands check the interaction to know whether they were invoked as a slash command."""
        self.assertIsNone(self.ctx.interaction)

    async def test_defer_does_nothing(self):
        """Commands can defer unconditionally."""
        self.assertIsNone(await self.ctx.defer())
        self.assertIsNone(await self.ctx.defer(ephemeral=True))

    async def test_send_uses_channel(self):
        """Messages are sent to the channel."""
        await self.ctx.send("content")
        self.channel.send.assert_awaited_once_with("content")
