import unittest
from unittest import mock

from bot.cogs.slowmode import Slowmode
from tests.helpers import MockBot, MockContext, MockTextChannel


class SlowmodeTests(unittest.IsolatedAsyncioTestCase):

    def setUp(self) -> None:
        self.bot = MockBot()
        self.cog = Slowmode(self.bot)
        self.text_channel = MockTextChannel()
        self.ctx = MockContext(channel=self.text_channel)

    async def test_get_slowmode_no_channel(self) -> None:
        """Get slowmode without a given channel"""
        self.text_channel.mention = '#python-general'
        self.text_channel.slowmode_delay = 5

        await self.cog.get_slowmode(self.cog, self.ctx, None)
        self.ctx.send.assert_called_once_with("The slowmode delay for #python-general is 5 seconds.")

    async def test_get_slowmode_with_channel(self) -> None:
        """Get slowmode without a given channel"""
        self.text_channel.mention = '#python-language'
        self.text_channel.slowmode_delay = 2

        await self.cog.get_slowmode(self.cog, self.ctx, self.text_channel)
        self.ctx.send.assert_called_once_with("The slowmode delay for #python-language is 2 seconds.")

    @mock.patch("bot.cogs.slowmode.with_role_check")
    @mock.patch("bot.cogs.slowmode.MODERATION_ROLES", new=(1, 2, 3))
    def test_cog_check(self, role_check):
        """Role check is called with `MODERATION_ROLES`"""
        self.cog.cog_check(self.ctx)
        role_check.assert_called_once_with(self.ctx, *(1, 2, 3))
