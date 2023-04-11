import unittest
from unittest import mock

from dateutil.relativedelta import relativedelta

from bot.constants import Emojis
from bot.exts.moderation.slowmode import Slowmode
from tests.helpers import MockBot, MockContext, MockTextChannel


class SlowmodeTests(unittest.IsolatedAsyncioTestCase):

    def setUp(self) -> None:
        self.bot = MockBot()
        self.cog = Slowmode(self.bot)
        self.ctx = MockContext()

    async def test_get_slowmode_no_channel(self) -> None:
        """Get slowmode without a given channel."""
        self.ctx.channel = MockTextChannel(name="python-general", slowmode_delay=5)

        await self.cog.get_slowmode(self.cog, self.ctx, None)
        self.ctx.send.assert_called_once_with("The slowmode delay for #python-general is 5 seconds.")

    async def test_get_slowmode_with_channel(self) -> None:
        """Get slowmode with a given channel."""
        text_channel = MockTextChannel(name="python-language", slowmode_delay=2)

        await self.cog.get_slowmode(self.cog, self.ctx, text_channel)
        self.ctx.send.assert_called_once_with("The slowmode delay for #python-language is 2 seconds.")

    async def test_set_slowmode_no_channel(self) -> None:
        """Set slowmode without a given channel."""
        test_cases = (
            ("helpers", 23, True, f"{Emojis.check_mark} The slowmode delay for #helpers is now 23 seconds."),
            ("mods", 76526, False, f"{Emojis.cross_mark} The slowmode delay must be between 0 and 6 hours."),
            ("admins", 97, True, f"{Emojis.check_mark} The slowmode delay for #admins is now 1 minute and 37 seconds.")
        )

        for channel_name, seconds, edited, result_msg in test_cases:
            with self.subTest(
                channel_mention=channel_name,
                seconds=seconds,
                edited=edited,
                result_msg=result_msg
            ):
                self.ctx.channel = MockTextChannel(name=channel_name)

                await self.cog.set_slowmode(self.cog, self.ctx, None, relativedelta(seconds=seconds))

                if edited:
                    self.ctx.channel.edit.assert_awaited_once_with(slowmode_delay=float(seconds))
                else:
                    self.ctx.channel.edit.assert_not_called()

                self.ctx.send.assert_called_once_with(result_msg)

            self.ctx.reset_mock()

    async def test_set_slowmode_with_channel(self) -> None:
        """Set slowmode with a given channel."""
        test_cases = (
            ("bot-commands", 12, True, f"{Emojis.check_mark} The slowmode delay for #bot-commands is now 12 seconds."),
            ("mod-spam", 21, True, f"{Emojis.check_mark} The slowmode delay for #mod-spam is now 21 seconds."),
            ("admin-spam", 4323598, False, f"{Emojis.cross_mark} The slowmode delay must be between 0 and 6 hours.")
        )

        for channel_name, seconds, edited, result_msg in test_cases:
            with self.subTest(
                channel_mention=channel_name,
                seconds=seconds,
                edited=edited,
                result_msg=result_msg
            ):
                text_channel = MockTextChannel(name=channel_name)

                await self.cog.set_slowmode(self.cog, self.ctx, text_channel, relativedelta(seconds=seconds))

                if edited:
                    text_channel.edit.assert_awaited_once_with(slowmode_delay=float(seconds))
                else:
                    text_channel.edit.assert_not_called()

                self.ctx.send.assert_called_once_with(result_msg)

            self.ctx.reset_mock()

    async def test_reset_slowmode_sets_delay_to_zero(self) -> None:
        """Reset slowmode with a given channel."""
        text_channel = MockTextChannel(name="meta", slowmode_delay=1)
        self.cog.set_slowmode = mock.AsyncMock()

        await self.cog.reset_slowmode(self.cog, self.ctx, text_channel)
        self.cog.set_slowmode.assert_awaited_once_with(
            self.ctx, text_channel, relativedelta(seconds=0)
        )

    @mock.patch("bot.exts.moderation.slowmode.has_any_role")
    @mock.patch("bot.exts.moderation.slowmode.MODERATION_ROLES", new=(1, 2, 3))
    async def test_cog_check(self, role_check):
        """Role check is called with `MODERATION_ROLES`"""
        role_check.return_value.predicate = mock.AsyncMock()
        await self.cog.cog_check(self.ctx)
        role_check.assert_called_once_with(*(1, 2, 3))
        role_check.return_value.predicate.assert_awaited_once_with(self.ctx)
