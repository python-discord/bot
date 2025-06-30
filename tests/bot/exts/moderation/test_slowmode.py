import asyncio
import datetime
from unittest import mock

from dateutil.relativedelta import relativedelta

from bot.constants import Emojis
from bot.exts.moderation.slowmode import Slowmode
from tests.base import RedisTestCase
from tests.helpers import MockBot, MockContext, MockTextChannel


class SlowmodeTests(RedisTestCase):

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

    @mock.patch("bot.exts.moderation.slowmode.datetime")
    async def test_set_slowmode_with_expiry(self, mock_datetime) -> None:
        """Set slowmode with an expiry"""
        fixed_datetime = datetime.datetime(2025, 6, 2, 12, 0, 0, tzinfo=datetime.UTC)
        mock_datetime.now.return_value = fixed_datetime

        test_cases = (
            ("python-general", 6, 6000, f"{Emojis.check_mark} The slowmode delay for #python-general is now 6 seconds "
             "and will revert to 0 seconds <t:1748871600:R>."),
            ("mod-spam", 5, 600, f"{Emojis.check_mark} The slowmode delay for #mod-spam is now 5 seconds and will "
             "revert to 0 seconds <t:1748866200:R>."),
            ("changelog", 12, 7200, f"{Emojis.check_mark} The slowmode delay for #changelog is now 12 seconds and will "
             "revert to 0 seconds <t:1748872800:R>.")
        )
        for channel_name, seconds, expiry, result_msg in test_cases:
            with self.subTest(
                channel_mention=channel_name,
                seconds=seconds,
                expiry=expiry,
                result_msg=result_msg
            ):
                text_channel = MockTextChannel(name=channel_name, slowmode_delay=0)
                await self.cog.set_slowmode(
                    self.cog,
                    self.ctx,
                    text_channel,
                    relativedelta(seconds=seconds),
                    fixed_datetime + relativedelta(seconds=expiry)
                )
                text_channel.edit.assert_awaited_once_with(slowmode_delay=float(seconds))
                self.ctx.send.assert_called_once_with(result_msg)
            self.ctx.reset_mock()

    async def test_callback_scheduled(self):
        """Schedule slowmode to be reverted"""
        self.cog.scheduler=mock.MagicMock(wraps=self.cog.scheduler)

        text_channel = MockTextChannel(name="python-general", slowmode_delay=2, id=123)
        expiry = datetime.datetime.now(tz=datetime.UTC) + relativedelta(seconds=10)
        await self.cog.set_slowmode(
            self.cog,
            self.ctx,
            text_channel,
            relativedelta(seconds=4),
            expiry
            )

        args = (expiry, text_channel.id, mock.ANY)
        self.cog.scheduler.schedule_at.assert_called_once_with(*args)

    @mock.patch("bot.exts.moderation.slowmode.get_or_fetch_channel")
    async def test_revert_slowmode_callback(self, mock_get_or_fetch_channel) -> None:
        """Check that the slowmode is reverted"""
        text_channel = MockTextChannel(name="python-general", slowmode_delay=2, id=123, jump_url="#python-general")
        mod_channel = MockTextChannel(name="mods", id=999, )
        # mock.MagicMock(return_value=text_channel)

        mock_get_or_fetch_channel.side_effect = [text_channel, mod_channel]

        await self.cog.set_slowmode(
            self.cog,
            self.ctx,
            text_channel,
            relativedelta(seconds=4),
            datetime.datetime.now(tz=datetime.UTC) + relativedelta(seconds=10)
            )
        await self.cog._revert_slowmode(text_channel.id)
        text_channel.edit.assert_awaited_with(slowmode_delay=2)
        mod_channel.send.assert_called_once_with(
            f"{Emojis.check_mark} A previously applied slowmode in {text_channel.jump_url} ({text_channel.id}) "
            "has expired and has been reverted to 2 seconds."
            )

    async def test_reschedule_slowmodes(self) -> None:
        """Does not reschedule if cache is empty"""
        self.cog.scheduler.schedule_at = mock.MagicMock()
        self.cog._reschedule = mock.AsyncMock()
        await self.cog.cog_unload()
        await self.cog.cog_load()

        self.cog._reschedule.assert_called()
        self.cog.scheduler.schedule_at.assert_not_called()

    async def test_reschedule_upon_reload(self) -> None:
        """ Check that method `_reschedule` is called upon cog reload"""
        self.cog._reschedule = mock.AsyncMock(wraps=self.cog._reschedule)
        await self.cog.cog_unload()
        await self.cog.cog_load()

        self.cog._reschedule.assert_called()

    async def test_reschedules_slowmodes(self) -> None:
        """Slowmodes are loaded from cache at cog reload and scheduled to be reverted."""

        now = datetime.datetime.now(tz=datetime.UTC)
        channels = {}
        slowmodes = (
            (123, (now - datetime.timedelta(minutes=10)), 2), # expiration in the past
            (456, (now + datetime.timedelta(minutes=20)), 4), # expiration in the future
        )
        for channel_id, expiration_datetime, delay in slowmodes:
            channel = MockTextChannel(slowmode_delay=delay, id=channel_id)
            channels[channel_id] = channel
            await self.cog.slowmode_cache.set(channel_id, f"{delay}, {expiration_datetime}")

        self.bot.get_channel = mock.MagicMock(side_effect=lambda channel_id: channels.get(channel_id))
        await self.cog.cog_unload()
        await self.cog.cog_load()
        for channel_id in channels:
            self.assertIn(channel_id, self.cog.scheduler)

        await asyncio.sleep(1) # give scheduled task time to execute
        channels[123].edit.assert_awaited_once_with(slowmode_delay=channels[123].slowmode_delay)
        channels[456].edit.assert_not_called()

    @mock.patch("bot.exts.moderation.slowmode.has_any_role")
    @mock.patch("bot.exts.moderation.slowmode.MODERATION_ROLES", new=(1, 2, 3))
    async def test_cog_check(self, role_check):
        """Role check is called with `MODERATION_ROLES`"""
        role_check.return_value.predicate = mock.AsyncMock()
        await self.cog.cog_check(self.ctx)
        role_check.assert_called_once_with(*(1, 2, 3))
        role_check.return_value.predicate.assert_awaited_once_with(self.ctx)
