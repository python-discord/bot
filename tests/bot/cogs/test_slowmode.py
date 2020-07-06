import unittest
from unittest import mock

from dateutil.relativedelta import relativedelta

from bot.cogs.slowmode import Slowmode
from bot.constants import Emojis
from tests.helpers import MockBot, MockContext, MockTextChannel


class SlowmodeTests(unittest.IsolatedAsyncioTestCase):

    def setUp(self) -> None:
        self.bot = MockBot()
        self.cog = Slowmode(self.bot)
        self.ctx = MockContext()

    async def test_get_slowmode_no_channel(self) -> None:
        """Get slowmode without a given channel."""
        self.ctx.channel = MockTextChannel(name='python-general', slowmode_delay=5)

        await self.cog.get_slowmode(self.cog, self.ctx, None)
        self.ctx.send.assert_called_once_with("The slowmode delay for #python-general is 5 seconds.")

    async def test_get_slowmode_with_channel(self) -> None:
        """Get slowmode with a given channel."""
        text_channel = MockTextChannel(name='python-language', slowmode_delay=2)

        await self.cog.get_slowmode(self.cog, self.ctx, text_channel)
        self.ctx.send.assert_called_once_with('The slowmode delay for #python-language is 2 seconds.')

    async def test_set_slowmode_no_channel(self) -> None:
        """Set slowmode without a given channel."""
        self.ctx.channel = MockTextChannel(name='careers')

        await self.cog.set_slowmode(self.cog, self.ctx, None, relativedelta(seconds=3))
        self.ctx.send.assert_called_once_with(
            f'{Emojis.check_mark} The slowmode delay for #careers is now 3 seconds.'
        )

    async def test_set_slowmode_with_channel(self) -> None:
        """Set slowmode with a given channel."""
        text_channel = MockTextChannel(name='meta')

        await self.cog.set_slowmode(self.cog, self.ctx, text_channel, relativedelta(seconds=4))
        self.ctx.send.assert_called_once_with(
            f'{Emojis.check_mark} The slowmode delay for #meta is now 4 seconds.'
        )

    async def test_reset_slowmode_no_channel(self) -> None:
        """Reset slowmode without a given channel."""
        self.ctx.channel = MockTextChannel(name='careers', slowmode_delay=6)

        await self.cog.reset_slowmode(self.cog, self.ctx, None)
        self.ctx.send.assert_called_once_with(
            f'{Emojis.check_mark} The slowmode delay for #careers has been reset to 0 seconds.'
        )

    async def test_reset_slowmode_with_channel(self) -> None:
        """Reset slowmode with a given channel."""
        text_channel = MockTextChannel(name='meta', slowmode_delay=1)

        await self.cog.reset_slowmode(self.cog, self.ctx, text_channel)
        self.ctx.send.assert_called_once_with(
            f'{Emojis.check_mark} The slowmode delay for #meta has been reset to 0 seconds.'
        )

    @mock.patch("bot.cogs.slowmode.with_role_check")
    @mock.patch("bot.cogs.slowmode.MODERATION_ROLES", new=(1, 2, 3))
    def test_cog_check(self, role_check):
        """Role check is called with `MODERATION_ROLES`"""
        self.cog.cog_check(self.ctx)
        role_check.assert_called_once_with(self.ctx, *(1, 2, 3))
