import unittest
from unittest import mock
from unittest.mock import MagicMock, Mock

from discord import PermissionOverwrite

from bot.cogs.moderation.silence import Silence, SilenceNotifier
from bot.constants import Channels, Emojis, Guild, Roles
from tests.helpers import MockBot, MockContext, MockTextChannel


class SilenceNotifierTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.alert_channel = MockTextChannel()
        self.notifier = SilenceNotifier(self.alert_channel)
        self.notifier.stop = self.notifier_stop_mock = Mock()
        self.notifier.start = self.notifier_start_mock = Mock()

    def test_add_channel_adds_channel(self):
        """Channel in FirstHash with current loop is added to internal set."""
        channel = Mock()
        with mock.patch.object(self.notifier, "_silenced_channels") as silenced_channels:
            self.notifier.add_channel(channel)
        silenced_channels.__setitem__.assert_called_with(channel, self.notifier._current_loop)

    def test_add_channel_starts_loop(self):
        """Loop is started if `_silenced_channels` was empty."""
        self.notifier.add_channel(Mock())
        self.notifier_start_mock.assert_called_once()

    def test_add_channel_skips_start_with_channels(self):
        """Loop start is not called when `_silenced_channels` is not empty."""
        with mock.patch.object(self.notifier, "_silenced_channels"):
            self.notifier.add_channel(Mock())
        self.notifier_start_mock.assert_not_called()

    def test_remove_channel_removes_channel(self):
        """Channel in FirstHash is removed from `_silenced_channels`."""
        channel = Mock()
        with mock.patch.object(self.notifier, "_silenced_channels") as silenced_channels:
            self.notifier.remove_channel(channel)
        silenced_channels.__delitem__.assert_called_with(channel)

    def test_remove_channel_stops_loop(self):
        """Notifier loop is stopped if `_silenced_channels` is empty after remove."""
        with mock.patch.object(self.notifier, "_silenced_channels", __bool__=lambda _: False):
            self.notifier.remove_channel(Mock())
        self.notifier_stop_mock.assert_called_once()

    def test_remove_channel_skips_stop_with_channels(self):
        """Notifier loop is not stopped if `_silenced_channels` is not empty after remove."""
        self.notifier.remove_channel(Mock())
        self.notifier_stop_mock.assert_not_called()

    async def test_notifier_private_sends_alert(self):
        """Alert is sent on 15 min intervals."""
        test_cases = (900, 1800, 2700)
        for current_loop in test_cases:
            with self.subTest(current_loop=current_loop):
                with mock.patch.object(self.notifier, "_current_loop", new=current_loop):
                    await self.notifier._notifier()
                self.alert_channel.send.assert_called_once_with(f"<@&{Roles.moderators}> currently silenced channels: ")
            self.alert_channel.send.reset_mock()

    async def test_notifier_skips_alert(self):
        """Alert is skipped on first loop or not an increment of 900."""
        test_cases = (0, 15, 5000)
        for current_loop in test_cases:
            with self.subTest(current_loop=current_loop):
                with mock.patch.object(self.notifier, "_current_loop", new=current_loop):
                    await self.notifier._notifier()
                    self.alert_channel.send.assert_not_called()


class SilenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.bot = MockBot()
        self.cog = Silence(self.bot)
        self.ctx = MockContext()
        self.cog._verified_role = None
        # Set event so command callbacks can continue.
        self.cog._get_instance_vars_event.set()

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
        """Proper reply after a successful unsilence."""
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
        self.assertFalse(channel.set_permissions.call_args.kwargs['send_messages'])

    async def test_silence_private_preserves_permissions(self):
        """Previous permissions were preserved when channel was silenced."""
        channel = MockTextChannel()
        # Set up mock channel permission state.
        mock_permissions = PermissionOverwrite()
        mock_permissions_dict = dict(mock_permissions)
        channel.overwrites_for.return_value = mock_permissions
        await self.cog._silence(channel, False, None)
        new_permissions = channel.set_permissions.call_args.kwargs
        # Remove 'send_messages' key because it got changed in the method.
        del new_permissions['send_messages']
        del mock_permissions_dict['send_messages']
        self.assertDictEqual(mock_permissions_dict, new_permissions)

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

    async def test_silence_private_added_muted_channel(self):
        """Channel was added to `muted_channels` on silence."""
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
        self.assertIsNone(channel.set_permissions.call_args.kwargs['send_messages'])

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
        muted_channels.discard.assert_called_once_with(channel)

    @mock.patch.object(Silence, "notifier", create=True)
    async def test_unsilence_private_preserves_permissions(self, _):
        """Previous permissions were preserved when channel was unsilenced."""
        channel = MockTextChannel()
        # Set up mock channel permission state.
        mock_permissions = PermissionOverwrite(send_messages=False)
        mock_permissions_dict = dict(mock_permissions)
        channel.overwrites_for.return_value = mock_permissions
        await self.cog._unsilence(channel)
        new_permissions = channel.set_permissions.call_args.kwargs
        # Remove 'send_messages' key because it got changed in the method.
        del new_permissions['send_messages']
        del mock_permissions_dict['send_messages']
        self.assertDictEqual(mock_permissions_dict, new_permissions)

    @mock.patch("bot.cogs.moderation.silence.asyncio")
    @mock.patch.object(Silence, "_mod_alerts_channel", create=True)
    def test_cog_unload_starts_task(self, alert_channel, asyncio_mock):
        """Task for sending an alert was created with present `muted_channels`."""
        with mock.patch.object(self.cog, "muted_channels"):
            self.cog.cog_unload()
            alert_channel.send.assert_called_once_with(f"<@&{Roles.moderators}> channels left silenced on cog unload: ")
            asyncio_mock.create_task.assert_called_once_with(alert_channel.send())

    @mock.patch("bot.cogs.moderation.silence.asyncio")
    def test_cog_unload_skips_task_start(self, asyncio_mock):
        """No task created with no channels."""
        self.cog.cog_unload()
        asyncio_mock.create_task.assert_not_called()

    @mock.patch("bot.cogs.moderation.silence.with_role_check")
    @mock.patch("bot.cogs.moderation.silence.MODERATION_ROLES", new=(1, 2, 3))
    def test_cog_check(self, role_check):
        """Role check is called with `MODERATION_ROLES`"""
        self.cog.cog_check(self.ctx)
        role_check.assert_called_once_with(self.ctx, *(1, 2, 3))
