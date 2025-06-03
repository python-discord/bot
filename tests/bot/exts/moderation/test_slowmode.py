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
    async def test_set_slowmode_with_duration(self, mock_datetime) -> None:
        """Set slowmode with a duration"""
        mock_datetime.now.return_value = datetime.datetime(2025, 6, 2, 12, 0, 0, tzinfo=datetime.UTC)
        test_cases = (
            ("python-general", 6, 6000, f"{Emojis.check_mark} The slowmode delay for #python-general is now 6 seconds"
             " and expires in <t:1748871600:R>."),
            ("mod-spam", 5, 600, f"{Emojis.check_mark} The slowmode delay for #mod-spam is now 5 seconds and expires"
             " in <t:1748866200:R>."),
            ("changelog", 12, 7200, f"{Emojis.check_mark} The slowmode delay for #changelog is now 12 seconds and"
             " expires in <t:1748872800:R>.")
        )
        for channel_name, seconds, duration, result_msg in test_cases:
            with self.subTest(
                channel_mention=channel_name,
                seconds=seconds,
                duration=duration,
                result_msg=result_msg
            ):
                text_channel = MockTextChannel(name=channel_name, slowmode_delay=0)
                await self.cog.set_slowmode(
                    self.cog,
                    self.ctx,
                    text_channel,
                    relativedelta(seconds=seconds),
                    duration=relativedelta(seconds=duration)
                )
                text_channel.edit.assert_awaited_once_with(slowmode_delay=float(seconds))
                self.ctx.send.assert_called_once_with(result_msg)
            self.ctx.reset_mock()

    @mock.patch("bot.exts.moderation.slowmode.datetime", wraps=datetime.datetime)
    async def test_callback_scheduled(self, mock_datetime, ):
        """Schedule slowmode to be reverted"""
        mock_now = datetime.datetime(2025, 6, 2, 12, 0, 0, tzinfo=datetime.UTC)
        mock_datetime.now.return_value = mock_now
        self.cog.scheduler=mock.MagicMock()

        text_channel = MockTextChannel(name="python-general", slowmode_delay=2, id=123)
        await self.cog.set_slowmode(
            self.cog,
            self.ctx,
            text_channel,
            relativedelta(seconds=4),
            relativedelta(seconds=10))

        args = (mock_now+relativedelta(seconds=10), text_channel.id, mock.ANY)
        self.cog.scheduler.schedule_at.assert_called_once_with(*args)

    async def test_revert_slowmode_callback(self) -> None:
        """Check that the slowmode is reverted"""
        text_channel = MockTextChannel(name="python-general", slowmode_delay=2, id=123)
        self.bot.get_channel = mock.MagicMock(return_value=text_channel)
        await self.cog.set_slowmode(
            self.cog, self.ctx, text_channel, relativedelta(seconds=4), relativedelta(seconds=10)
            )
        await self.cog._revert_slowmode(text_channel.id)
        text_channel.edit.assert_awaited_with(slowmode_delay=2)
        text_channel.send.assert_called_once_with(
            f"{Emojis.check_mark} A previously applied slowmode has expired and has been reverted to 2 seconds."
            )

    async def test_reschedule_slowmodes(self) -> None:
        """Does not reschedule if cache is empty"""
        self.cog.scheduler.schedule_at = mock.MagicMock()
        self.cog._reschedule = mock.AsyncMock()
        await self.cog.cog_unload()
        await self.cog.cog_load()

        self.cog._reschedule.assert_called()
        self.cog.scheduler.schedule_at.assert_not_called()


    @mock.patch("bot.exts.moderation.slowmode.datetime", wraps=datetime.datetime)
    async def test_reschedules_slowmodes(self, mock_datetime) -> None:
        """Slowmodes are loaded from cache at cog reload and scheduled to be reverted."""
        mock_datetime.now.return_value = datetime.datetime(2025, 6, 2, 12, 0, 0, tzinfo=datetime.UTC)
        mock_now = datetime.datetime(2025, 6, 2, 12, 0, 0, tzinfo=datetime.UTC)
        self.cog._reschedule = mock.AsyncMock(wraps=self.cog._reschedule)

        channels = []
        slowmodes = (
            (123, (mock_now - datetime.timedelta(10)).timestamp(), 2), # expiration in the past
            (456, (mock_now + datetime.timedelta(10)).timestamp(), 4), # expiration in the future
        )

        for channel_id, expiration_datetime, delay in slowmodes:
            channel = MockTextChannel(slowmode_delay=delay, id=channel_id)
            channels.append(channel)

            await self.cog.slowmode_expiration_cache.set(channel_id, expiration_datetime)
            await self.cog.original_slowmode_cache.set(channel_id, delay)

        await self.cog.cog_unload()
        await self.cog.cog_load()

        # check that _reschedule function was called upon cog reload.
        self.cog._reschedule.assert_called()

        # check that a task was created for every cached slowmode.
        for channel in channels:
            self.assertIn(channel.id, self.cog.scheduler)

        # check that one channel with slowmode expiration in the past was edited immediately.
        channels[0].edit.assert_awaited_once_with(slowmode_delay=channels[0].slowmode_delay)
        channels[1].edit.assert_not_called()

    @mock.patch("bot.exts.moderation.slowmode.has_any_role")
    @mock.patch("bot.exts.moderation.slowmode.MODERATION_ROLES", new=(1, 2, 3))
    async def test_cog_check(self, role_check):
        """Role check is called with `MODERATION_ROLES`"""
        role_check.return_value.predicate = mock.AsyncMock()
        await self.cog.cog_check(self.ctx)
        role_check.assert_called_once_with(*(1, 2, 3))
        role_check.return_value.predicate.assert_awaited_once_with(self.ctx)
