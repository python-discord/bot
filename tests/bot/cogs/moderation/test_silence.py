import unittest
from unittest import mock
from unittest.mock import MagicMock, Mock

from bot.cogs.moderation.silence import FirstHash, Silence
from bot.constants import Emojis
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


class SilenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.bot = MockBot()
        self.cog = Silence(self.bot)
        self.ctx = MockContext()
        self.cog._verified_role = None

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
                    self.ctx.send.call_args.assert_called_once_with(result_message)

    async def test_unsilence_sent_correct_discord_message(self):
        """Check if proper message was sent to `alert_chanel`."""
        with mock.patch.object(self.cog, "_unsilence", return_value=True):
            await self.cog.unsilence.callback(self.cog, self.ctx)
            self.ctx.send.call_args.assert_called_once_with(f"{Emojis.check_mark} unsilenced current channel.")

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
            await self.cog._silence(MockTextChannel(), False, None)
        muted_channels.add.call_args.assert_called_once_with(channel)

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
        notifier.remove_channel.call_args.assert_called_once_with(channel)

    @mock.patch.object(Silence, "notifier", create=True)
    async def test_unsilence_private_removed_muted_channel(self, _):
        """Channel was removed from `muted_channels` on unsilence."""
        perm_overwrite = MagicMock(send_messages=False)
        channel = MockTextChannel(overwrites_for=Mock(return_value=perm_overwrite))
        with mock.patch.object(self.cog, "muted_channels") as muted_channels:
            await self.cog._unsilence(channel)
        muted_channels.remove.call_args.assert_called_once_with(channel)
