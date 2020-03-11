import unittest
from unittest import mock
from unittest.mock import MagicMock, Mock

from bot.cogs.moderation.silence import FirstHash, Silence, SilenceNotifier
from bot.constants import Channels, Emojis, Guild, Roles
from tests.helpers import MockBot, MockContext, MockTextChannel


class FirstHashTests(unittest.TestCase):
    def setUp(self) -> None:
        self.test_cases = (
            (FirstHash(0, 4), FirstHash(0, 5)),
            (FirstHash("string", None), FirstHash("string", True))
        )

    def test_hashes_equal(self):
        """Check hashes equal with same first item."""

        for tuple1, tuple2 in self.test_cases:
            with self.subTest(tuple1=tuple1, tuple2=tuple2):
                self.assertEqual(hash(tuple1), hash(tuple2))

    def test_eq(self):
        """Check objects are equal with same first item."""

        for tuple1, tuple2 in self.test_cases:
            with self.subTest(tuple1=tuple1, tuple2=tuple2):
                self.assertTrue(tuple1 == tuple2)


class SilenceNotifierTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.alert_channel = MockTextChannel()
        self.notifier = SilenceNotifier(self.alert_channel)


class SilenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.bot = MockBot()
        self.cog = Silence(self.bot)
        self.ctx = MockContext()
        self.cog._verified_role = None

    async def test_instance_vars_got_guild(self):
        """Bot got guild after it became available."""
        await self.cog._get_instance_vars()
        self.bot.wait_until_guild_available.assert_called_once()
        self.bot.get_guild.assert_called_once_with(Guild.id)

    async def test_instance_vars_got_role(self):
        """Got `Roles.verified` role from guild."""
        await self.cog._get_instance_vars()
        guild = self.bot.get_guild()
        guild.get_role.assert_called_once_with(Roles.verified)

    async def test_instance_vars_got_channels(self):
        """Got channels from bot."""
        await self.cog._get_instance_vars()
        self.bot.get_channel.called_once_with(Channels.mod_alerts)
        self.bot.get_channel.called_once_with(Channels.mod_log)

    @mock.patch("bot.cogs.moderation.silence.SilenceNotifier")
    async def test_instance_vars_got_notifier(self, notifier):
        """Notifier was started with channel."""
        mod_log = MockTextChannel()
        self.bot.get_channel.side_effect = (None, mod_log)
        await self.cog._get_instance_vars()
        notifier.assert_called_once_with(mod_log)
        self.bot.get_channel.side_effect = None

    async def test_silence_sent_correct_discord_message(self):
        """Check if proper message was sent when called with duration in channel with previous state."""
        test_cases = (
            (0.0001, f"{Emojis.check_mark} silenced current channel for 0.0001 minute(s).", True,),
            (None, f"{Emojis.check_mark} silenced current channel indefinitely.", True,),
            (5, f"{Emojis.cross_mark} current channel is already silenced.", False,),
        )
        for duration, result_message, _silence_patch_return in test_cases:
            with self.subTest(
                    silence_duration=duration,
                    result_message=result_message,
                    starting_unsilenced_state=_silence_patch_return
            ):
                with mock.patch.object(self.cog, "_silence", return_value=_silence_patch_return):
                    await self.cog.silence.callback(self.cog, self.ctx, duration)
                    self.ctx.send.assert_called_once_with(result_message)
            self.ctx.reset_mock()

    async def test_unsilence_sent_correct_discord_message(self):
        """Check if proper message was sent to `alert_chanel`."""
        with mock.patch.object(self.cog, "_unsilence", return_value=True):
            await self.cog.unsilence.callback(self.cog, self.ctx)
            self.ctx.send.assert_called_once_with(f"{Emojis.check_mark} unsilenced current channel.")

    async def test_silence_private_for_false(self):
        """Permissions are not set and `False` is returned in an already silenced channel."""
        perm_overwrite = Mock(send_messages=False)
        channel = Mock(overwrites_for=Mock(return_value=perm_overwrite))

        self.assertFalse(await self.cog._silence(channel, True, None))
        channel.set_permissions.assert_not_called()

    async def test_silence_private_silenced_channel(self):
        """Channel had `send_message` permissions revoked."""
        channel = MockTextChannel()
        self.assertTrue(await self.cog._silence(channel, False, None))
        channel.set_permissions.assert_called_once()
        self.assertFalse(channel.set_permissions.call_args.kwargs['overwrite'].send_messages)

    async def test_silence_private_notifier(self):
        """Channel should be added to notifier with `persistent` set to `True`, and the other way around."""
        channel = MockTextChannel()
        with mock.patch.object(self.cog, "notifier", create=True):
            with self.subTest(persistent=True):
                await self.cog._silence(channel, True, None)
                self.cog.notifier.add_channel.assert_called_once()

        with mock.patch.object(self.cog, "notifier", create=True):
            with self.subTest(persistent=False):
                await self.cog._silence(channel, False, None)
                self.cog.notifier.add_channel.assert_not_called()

    async def test_silence_private_removed_muted_channel(self):
        channel = MockTextChannel()
        with mock.patch.object(self.cog, "muted_channels") as muted_channels:
            await self.cog._silence(channel, False, None)
        muted_channels.add.assert_called_once_with(channel)

    async def test_unsilence_private_for_false(self):
        """Permissions are not set and `False` is returned in an unsilenced channel."""
        channel = Mock()
        self.assertFalse(await self.cog._unsilence(channel))
        channel.set_permissions.assert_not_called()

    @mock.patch.object(Silence, "notifier", create=True)
    async def test_unsilence_private_unsilenced_channel(self, _):
        """Channel had `send_message` permissions restored"""
        perm_overwrite = MagicMock(send_messages=False)
        channel = MockTextChannel(overwrites_for=Mock(return_value=perm_overwrite))
        self.assertTrue(await self.cog._unsilence(channel))
        channel.set_permissions.assert_called_once()
        self.assertTrue(channel.set_permissions.call_args.kwargs['overwrite'].send_messages)

    @mock.patch.object(Silence, "notifier", create=True)
    async def test_unsilence_private_removed_notifier(self, notifier):
        """Channel was removed from `notifier` on unsilence."""
        perm_overwrite = MagicMock(send_messages=False)
        channel = MockTextChannel(overwrites_for=Mock(return_value=perm_overwrite))
        await self.cog._unsilence(channel)
        notifier.remove_channel.assert_called_once_with(channel)

    @mock.patch.object(Silence, "notifier", create=True)
    async def test_unsilence_private_removed_muted_channel(self, _):
        """Channel was removed from `muted_channels` on unsilence."""
        perm_overwrite = MagicMock(send_messages=False)
        channel = MockTextChannel(overwrites_for=Mock(return_value=perm_overwrite))
        with mock.patch.object(self.cog, "muted_channels") as muted_channels:
            await self.cog._unsilence(channel)
        muted_channels.remove.assert_called_once_with(channel)

    @mock.patch("bot.cogs.moderation.silence.asyncio")
    @mock.patch.object(Silence, "_mod_alerts_channel", create=True)
    def test_cog_unload(self, alert_channel, asyncio_mock):
        """Task for sending an alert was created with present `muted_channels`."""
        with mock.patch.object(self.cog, "muted_channels"):
            self.cog.cog_unload()
            asyncio_mock.create_task.assert_called_once_with(alert_channel.send())
            alert_channel.send.called_once_with(f"<@&{Roles.moderators}> chandnels left silenced on cog unload: ")

    @mock.patch("bot.cogs.moderation.silence.asyncio")
    def test_cog_unload1(self, asyncio_mock):
        """No task created with no channels."""
        self.cog.cog_unload()
        asyncio_mock.create_task.assert_not_called()

    @mock.patch("bot.cogs.moderation.silence.with_role_check")
    @mock.patch("bot.cogs.moderation.silence.MODERATION_ROLES", new=(1, 2, 3))
    def test_cog_check(self, role_check):
        """Role check is called with `MODERATION_ROLES`"""
        self.cog.cog_check(self.ctx)
        role_check.assert_called_once_with(self.ctx, *(1, 2, 3))
